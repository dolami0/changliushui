"""
定时轮询调度器 (V5) — 按固定间隔查询 Agent0 表，触发 V5 4-Agent 管线处理。

使用 asyncio 事件循环 + 可配置间隔。
通过 FastAPI lifespan 事件启动/停止。
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class Scheduler:
    """定时轮询 Coze Agent0 表，发现未完成记录后触发 V5 管线。"""

    def __init__(self, coze_client, pipeline_runner, config: dict):
        self.coze = coze_client
        self.runner = pipeline_runner
        self.agent0_db_id = config["agent0_database_id"]
        self.output_db_id = config.get("output_database_id", "")
        self.interval = config.get("polling_interval_sec", 600)
        self.server_port = config.get("server_port", 8080)
        self._task: asyncio.Task | None = None
        self._running = False
        self.last_poll_at: str | None = None
        self.next_poll_at: str | None = None
        # 运行时状态（供 dashboard 查询）
        self.active_jobs: list[dict] = []
        self.completed_jobs: list[dict] = []
        self.current_poll_status: str = "idle"
        self._latest_review: dict | None = None  # 最新一轮审阅结果

    async def start(self):
        """启动定时轮询（由 FastAPI lifespan 调用）"""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"V5调度器已启动，轮询间隔 {self.interval}s")

    async def stop(self):
        """停止调度器"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("V5调度器已停止")

    async def poll_now(self) -> list[dict]:
        """手动触发一轮轮询"""
        return await self._poll()

    @staticmethod
    def _next_hour_local() -> datetime:
        now_local = datetime.now()
        next_local = now_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return next_local.astimezone(timezone.utc)

    async def _loop(self):
        """主循环：每整点轮询 (北京时间)"""
        await asyncio.sleep(3)
        while self._running:
            next_hour = self._next_hour_local()
            now_utc = datetime.now(timezone.utc)
            wait_sec = max(10, (next_hour - now_utc).total_seconds())
            self.next_poll_at = next_hour.isoformat()
            logger.info(f"下次轮询: {next_hour.isoformat()} (等待 {wait_sec:.0f}s, 配置间隔 {self.interval}s)")
            await asyncio.sleep(wait_sec)
            if not self._running:
                break
            try:
                await self._poll()
            except Exception as e:
                logger.error(f"轮询异常: {e}")

    async def _poll(self) -> list[dict]:
        """执行一轮：查询 → 批量处理 → 写结果"""
        self.current_poll_status = "polling"
        self.last_poll_at = datetime.now(timezone.utc).isoformat()
        try:
            return await asyncio.to_thread(self._poll_sync)
        except Exception:
            self.current_poll_status = "idle"
            raise

    def _poll_sync(self) -> list[dict]:
        try:
            return self._poll_sync_inner()
        finally:
            self.current_poll_status = "idle"
            self.active_jobs = []

    def _poll_sync_inner(self) -> list[dict]:
        # 1. 查询未完成记录
        records = self.coze.query_incomplete_records(self.agent0_db_id)
        if not records:
            logger.info("本轮无待处理记录")
            return []

        logger.info(f"发现 {len(records)} 条待处理记录")
        self.active_jobs = [{"stock_code": r.get("stock_code", "?"),
                             "stock_name": r.get("stock_name", "?"),
                             "status": "queued"} for r in records]

        # 2. 获取 DeepSeek API Key
        config_path = Path(__file__).resolve().parent / "config.json"
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        deepseek_key = cfg.get("deepseek_api_key", "") or os.environ.get("DEEPSEEK_API_KEY", "")

        # 3. 逐条处理 — V5 4-Agent 管线
        results = []
        job_statuses: list[dict] = []  # 用本地列表替代 self.active_jobs[i]
        for i, rec in enumerate(records):
            if not self._running:
                logger.info("调度器已停止，中断批处理")
                break

            # 脏数据卫生检查：stock_code 为空直接跳过并标记完成，等待人工核查
            stock_code = (rec.get("stock_code", "") or "").strip()
            if not stock_code:
                record_id = rec.get("id", "")
                logger.warning(f"跳过无效记录 (stock_code为空): id={record_id} name={rec.get('stock_name','?')}")
                if record_id:
                    try:
                        self.coze.mark_record_complete(self.agent0_db_id, record_id)
                    except Exception:
                        logger.error(f"标记无效记录失败: id={record_id}")
                continue

            job = {"stock_code": stock_code,
                   "stock_name": rec.get("stock_name", "?"),
                   "status": "running"}
            job_statuses.append(job)
            self.active_jobs = job_statuses

            try:
                result = self.runner.run_single(rec, deepseek_key)
                results.append(result)

                if result.get("status") == "done":
                    stock_code = rec.get("stock_code", "")
                    stock_name = rec.get("stock_name", "")

                    # Report 阶段: 写入 Coze + 保存报告
                    self._emit_report_progress(stock_code, stock_name, 1, 2,
                                               "写入Coze输出表", "running")
                    ts = datetime.now().strftime("%Y%m%d_%H%M")
                    if self.output_db_id:
                        try:
                            ts = self._write_result_to_coze_v5(rec, result, deepseek_key)
                        except Exception as e:
                            ts = datetime.now().strftime("%Y%m%d_%H%M")
                            logger.error(f"写入输出表失败: {e}")
                    # 无论 Coze 写入是否成功，都标记 agent0 记录为完成
                    record_id = rec.get("id", "")
                    if record_id:
                        try:
                            self.coze.mark_record_complete(self.agent0_db_id, record_id)
                        except Exception as e:
                            logger.error(f"标记记录完成失败: {e}")
                    self._emit_report_progress(stock_code, stock_name, 1, 2,
                                               "写入Coze输出表", "done")

                    # Report 阶段: step 2 构建 HTML
                    self._emit_report_progress(stock_code, stock_name, 2, 2,
                                               "构建Markdown报告", "running")
                    self._emit_report_progress(stock_code, stock_name, 2, 2,
                                               "构建Markdown报告", "done")

                    job["status"] = "done"
                    report_url = f"http://localhost:{self.server_port}/report/{stock_code}_{ts}"
                    self.completed_jobs.append({
                        "stock_code": stock_code,
                        "stock_name": stock_name,
                        "status": "done",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "report_url": report_url,
                        "quality_flag": result.get("agent3", {}).get("valuation_summary", {}).get("quality_flag", ""),
                        "upside_pct": result.get("agent3", {}).get("valuation_summary", {}).get("probability_weighted_upside_pct", 0),
                    })
                else:
                    job["status"] = "error"
                    logger.error(f"管线处理失败: {rec.get('stock_code')} — "
                                 f"{result.get('error','未知错误')[:120]}")

            except Exception as e:
                logger.error(f"处理 {rec.get('stock_code', '?')} 失败: {e}")
                job["status"] = "error"
                results.append({"agent0": rec, "status": "error", "error": str(e)})

        # 4. 跨股赔率排序
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
            from ranking_engine import compute_ranking
            compute_ranking(results)
            logger.info("赔率排序完成")
        except Exception as e:
            logger.warning(f"赔率排序跳过: {e}")

        # 5. 每日报告审阅
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
            from report_reviewer import review_batch
            done_results = [r for r in results if r.get("status") == "done"]
            if len(done_results) >= 1:
                review_summary = review_batch(done_results)
                self._write_review_report(review_summary, done_results)
                self._latest_review = review_summary
                logger.info(f"每日审阅完成: 评级分布={review_summary.get('grade_distribution',{})}")
        except Exception as e:
            logger.warning(f"每日审阅跳过: {e}")

        self.next_poll_at = Scheduler._next_hour_local().isoformat()
        return results

    # ═══════════════════════════════════════
    # 每日审阅报告
    # ═══════════════════════════════════════

    REVIEW_DIR = Path(__file__).resolve().parent.parent / "reports" / "reviews"
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _write_review_report(cls, review_summary: dict, results: list[dict]):
        """将每日审阅结果写入 Markdown 文件。"""
        now = datetime.now().strftime("%Y-%m-%d")
        path = cls.REVIEW_DIR / f"review_{now}.md"

        lines = [
            f"# 每日报告审阅 — {now}",
            "",
            f"**审阅报告数**: {review_summary.get('total_reports', 0)}",
            f"**系统健康度**: {review_summary.get('overall_health', '?')}",
            "",
            "## 评级分布",
            "",
        ]
        for grade, count in sorted(review_summary.get("grade_distribution", {}).items()):
            bar = "█" * count
            lines.append(f"- **{grade}**: {bar} ({count}份)")

        lines.extend([
            "",
            "## 各层平均分",
            "",
            "| 层级 | 均分 | 状态 |",
            "|------|:----:|------|",
        ])
        for layer, avg in review_summary.get("layer_averages", {}).items():
            status = "" if avg >= 8 else ("️" if avg >= 6 else "")
            lines.append(f"| {layer} | {avg}/10 | {status} |")

        lines.extend([
            "",
            "## 系统性高频问题",
            "",
        ])
        top_flags = review_summary.get("top_systemic_flags", [])
        if top_flags:
            for f in top_flags:
                lines.append(f"- **{f['code']}** ({f['count']}次): {f['action']}")
        else:
            lines.append("无系统性高频问题 ")

        lines.extend([
            "",
            "## 个股审阅详情",
            "",
        ])
        for r in results:
            if r.get("status") != "done":
                continue
            a3 = r.get("agent3", {})
            vs = a3.get("valuation_summary", {})
            # 多路径提取 stock_code / stock_name（V5 V4 格式兼容）
            a0 = r.get("agent0", {})
            a1 = r.get("agent1", {})
            code = a1.get("stock_code", "") or a0.get("stock_code", "?")
            name = (
                a0.get("stock_name", "")
                or a1.get("packages", {}).get("core", {}).get("fields", {}).get("stock_name", "")
                or a1.get("clean_financials", {}).get("stock_name", "")
                or code
            )
            upside = vs.get("probability_weighted_upside_pct", 0)
            asym = vs.get("asymmetry_ratio", 0)
            quality = vs.get("quality_flag", "?")

            # 重新跑审阅取评级
            try:
                from report_reviewer import review_from_orchestrator_result
                rev = review_from_orchestrator_result(r)
                grade = rev.overall_grade
                flag_codes = [f.code for f in rev.flags if f.severity != "info"]
            except Exception:
                grade = "?"
                flag_codes = []

            flag_str = ", ".join(flag_codes) if flag_codes else "无"
            lines.append(f"### {name}({code}) — {grade}")
            lines.append(f"- 加权涨幅: {upside:+.1f}% | 不对称比: {asym:.1f}x | 质量: {quality}")
            lines.append(f"- 标记: {flag_str}")
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"审阅报告已保存: {path}")

    # ═══════════════════════════════════════
    # V5 → V4 兼容层
    # ═══════════════════════════════════════

    @staticmethod
    def _v5_to_v4_compat(result: dict) -> tuple[dict, dict, dict]:
        """将 V5 输出转换为 V4 兼容格式，供 report_builder 和 Coze 表消费。"""
        # 防御: 确保顶层值是 dict
        a1_raw = result.get("agent1", {}) if isinstance(result.get("agent1"), dict) else {}
        a2_raw = result.get("agent2", {}) if isinstance(result.get("agent2"), dict) else {}
        a3_raw = result.get("agent3", {}) if isinstance(result.get("agent3"), dict) else {}

        # 提取核心字段（兼容 packages.core.fields 和 flat clean_financials）
        pkgs = a1_raw.get("packages", {}) if isinstance(a1_raw.get("packages"), dict) else {}
        core = pkgs.get("core", {}).get("fields", {}) if isinstance(pkgs.get("core"), dict) else {}
        if not core:
            core = a1_raw.get("clean_financials", {}) if isinstance(a1_raw.get("clean_financials"), dict) else {}

        # 字段名兼容：旧版 frozen 数据用 operating_cf_ttm_yi，新版用 ocf_ttm_yi
        if "ocf_ttm_yi" not in core and "operating_cf_ttm_yi" in core:
            core["ocf_ttm_yi"] = core["operating_cf_ttm_yi"]

        # Agent3 的子结构
        ms = a3_raw.get("market_sanity", {}) if isinstance(a3_raw.get("market_sanity"), dict) else {}
        # valuation_routing: Agent-2 产出 routing_decision，Agent-3 可能输出空壳 {primary_model:""}
        # 优先用 Agent-2 的真实数据，仅当 Agent-3 有实质内容时才用 Agent-3 的
        vr_a3 = a3_raw.get("valuation_routing", {}) if isinstance(a3_raw.get("valuation_routing"), dict) else {}
        vr_a2 = a2_raw.get("routing_decision", {}) if isinstance(a2_raw.get("routing_decision"), dict) else {}
        vr = vr_a2 if vr_a2.get("primary_model") and not vr_a3.get("primary_model") else (vr_a3 if vr_a3.get("primary_model") else vr_a2)
        sv = a3_raw.get("scenario_valuation", {})
        rd = a3_raw.get("reverse_dcf", {})
        vs = a3_raw.get("valuation_summary", {})

        # 补全 core 中的计算字段
        if "report_period" not in core or not core["report_period"]:
            core["report_period"] = ms.get("report_period", "")

        # 补 secondary_model
        secondary = vr.get("secondary_model", "") or vr.get("validation_models", [None])[0] or ""
        vr_fixed = {**vr, "secondary_model": secondary}

        # V4-compatible a1（移除 V5 不再产出的空壳字段）
        implied_g = ms.get("implied_g_pct", 0) or 0
        roic_va = core.get("roic_pct", 0) or 0
        implied_rr = round(implied_g / roic_va * 100, 1) if roic_va > 0 else None
        a1_v4 = {
            "clean_financials": core,
            "valuation_anchor": {
                "pe_ttm": core.get("pe_ttm", 0),
                "pb": core.get("pb", 0),
                "ev_yi": ms.get("ev_yi"),
                "nopat_yi": core.get("nopat_yi"),
                "roic_pct": core.get("roic_pct"),
                "wacc_mid_pct": ms.get("wacc_simple_pct"),
                "wacc_params": ms.get("wacc_params", {}),
                "valuation_model": vr.get("primary_model", ""),
                "implied_rr_pct": implied_rr,
            },
            "valuation_routing": vr_fixed,
            "market_sanity": ms,
            "forward_looking": core.pop("_forward_looking", {
                "status": "unavailable", "categories": {}, "text_summary": ""
            }),
        }

        # V4-compatible a2
        cm_all = a2_raw.get("case_matches_all", [])
        cm_top3 = a2_raw.get("case_matches_top3", [])
        details = sv.get("scenario_details", {})
        base_detail = details.get("base", {})

        # 补全 scenario_details 中的计算字段（nopat_growth = ROIC × RR, wacc 来自 BS）
        wacc_pct = ms.get("wacc_simple_pct", 9.5)
        enriched_details = {}
        for name, d in details.items():
            roic = d.get("roic_assumed_pct", 0)
            rr = d.get("rr_assumed_pct", 0)
            g = round(roic * rr / 100, 1) if roic and rr else None
            enriched_details[name] = {
                **d,
                "nopat_growth_pct": g,
                "wacc_used_pct": wacc_pct,
            }

        # 从 case_comparison_summary 提取 6 维判断
        cc_v5 = a3_raw.get("case_comparison_summary", {})
        cc_cases = cc_v5.get("compared_cases", [])
        cc_map = {c.get("case_code", ""): c.get("six_dimension_judgment", {}) for c in cc_cases}

        # 构建 a2（移除 V4-only 空壳）
        a2_v4 = {
            "dcf_results": {
                "valuation_approach": vr_fixed.get("method_used", vr_fixed.get("primary_model", "")),
                "scenario_details": enriched_details,
            },
            "case_comparison": [
                {"case_code": m.get("case_code", ""),
                 "comprehensive_discount_pct": m.get("comprehensive_discount_pct",
                                                     100 - m.get("score", 0) * 6),
                 "six_dimension_judgment": cc_map.get(m.get("case_code", ""), {})}
                for m in (cc_cases if cc_cases else [
                    {"case_code": m.get("case_code", ""), "score": m.get("score", 0)}
                    for m in cm_top3
                ])
            ],
            "similar_cases": [m.get("case_code", "") for m in cm_all],
            "web_search_summary": a2_raw.get("web_search_summary", {}),
        }

        return a1_v4, a2_v4, a3_raw

    # ═══════════════════════════════════════
    # Coze 输出表写入 (V5)
    # ═══════════════════════════════════════

    def _write_result_to_coze_v5(self, agent0_record: dict, result: dict, deepseek_key: str):
        """V5 版本：将管线结果写入 Coze 输出表 + 生成 HTML 报告 + 保存 JSON。"""
        from valuation_app.report_builder import build_markdown_report, save_report

        stock_code = agent0_record.get("stock_code", "")
        stock_name = agent0_record.get("stock_name", "")
        ts = datetime.now().strftime("%Y%m%d_%H%M")

        # ── Step 1: 先保存原始 JSON（不依赖 V4 compat，确保数据不丢失）──
        data_dir = Path(__file__).resolve().parent.parent / "reports" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        json_path = data_dir / f"{stock_code}_{ts}.json"
        raw_agent2 = result.get("agent2", {}) if isinstance(result.get("agent2"), dict) else {}
        raw_routing = raw_agent2.get("routing_decision", {}) if isinstance(raw_agent2.get("routing_decision"), dict) else {}
        a2a_raw = result.get("agent2a", {}) if isinstance(result.get("agent2a"), dict) else {}

        # ── Step 2: V5→V4 兼容转换（可能失败，但不影响 JSON 保存）──
        try:
            a1_out, a2_out, a3_out = self._v5_to_v4_compat(result)
        except Exception as e:
            logger.error(f"V5→V4 compat 转换失败: {e}")
            # 用空结构兜底，JSON 已在上一步保存
            a1_out = {"clean_financials": {}, "valuation_anchor": {}, "valuation_routing": {}, "market_sanity": {}}
            a2_out = {}
            a3_out = {"valuation_summary": {}, "scenarios": [], "confidence": {}, "trade_annotation": {}}

        cf = a1_out.get("clean_financials", {})
        vr = a1_out.get("valuation_routing", {})
        vs = a3_out.get("valuation_summary", {})
        conf = a3_out.get("confidence", {})
        ta = a3_out.get("trade_annotation", {})
        scenarios = a3_out.get("scenarios", [])

        # 解析三情景
        bear = next((s for s in scenarios if isinstance(s, dict) and "bear" in str(s.get("name", "")).lower()), {})
        base = next((s for s in scenarios if isinstance(s, dict) and "base" in str(s.get("name", "")).lower()), {})
        bull = next((s for s in scenarios if isinstance(s, dict) and "bull" in str(s.get("name", "")).lower()), {})

        # 生成 Markdown 报告
        try:
            md = build_markdown_report(agent0_record, a1_out, a2_out, a3_out, a2a_raw)
            report_path = save_report(md, stock_code, ts=ts)
        except Exception as e:
            logger.error(f"报告生成失败: {e}")
            report_path = ""

        # ── Step 3: 写入 Coze 输出表 ──
        row = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "event_date": agent0_record.get("bstudio_create_time", ""),
            "event_source": agent0_record.get("event_source", ""),
            "primary_model": vr.get("primary_model", ""),
            "prob_weighted_upside_pct": str(vs.get("probability_weighted_upside_pct", "")),
            "asymmetry_ratio": str(vs.get("asymmetry_ratio", "")),
            "quality_flag": vs.get("quality_flag", ""),
            "current_mcap_billion": str(cf.get("market_cap_yi", "")),
            "prob_weighted_mcap_billion": str(vs.get("probability_weighted_mcap_yi", "")),
            "bear_prob": str(bear.get("probability_pct", "")),
            "bear_upside_pct": str(bear.get("upside_pct", "")),
            "base_prob": str(base.get("probability_pct", "")),
            "base_upside_pct": str(base.get("upside_pct", "")),
            "bull_prob": str(bull.get("probability_pct", "")),
            "bull_upside_pct": str(bull.get("upside_pct", "")),
            "confidence_score": str(conf.get("overall_score", "")),
            "trade_tier": ta.get("tier", ""),
            "report_html_url": f"http://localhost:{self.server_port}/report/{stock_code}_{ts}",
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.coze.insert_records(self.output_db_id, [row])
        except Exception as e:
            logger.error(f"写入Coze输出表失败: {e}")

        # ── Step 4: 保存完整结构化 JSON ──
        payload = {
            "agent0": agent0_record,
            "agent1": self._serialize_agent_output(a1_out),
            "agent2": self._serialize_agent_output(a2_out),
            "agent2a": self._serialize_agent_output(a2a_raw) if a2a_raw else {},
            "agent3": self._serialize_agent_output(a3_out),
            "routing_decision": raw_routing,  # V6: 保留原始路由判决
            "_pipeline_version": "6.0",
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

        # V6: 自动构建评测记录（时间冻结）
        try:
            from evals.eval_builder import build_eval_record
            eval_id = build_eval_record(agent0_record, result, a1_out)
            logger.info(f"[Eval] 评测记录已保存: {eval_id}")
        except Exception as e:
            logger.warning(f"[Eval] 评测记录保存失败: {e}")

        logger.info(f"[V5] 结果已写入输出表: {stock_code} — 报告: {report_path}")
        return ts

    @staticmethod
    def _serialize_agent_output(obj) -> dict:
        """将 Agent 输出转为 JSON 可序列化格式"""
        if isinstance(obj, dict):
            return {k: Scheduler._serialize_agent_output(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [Scheduler._serialize_agent_output(v) for v in obj]
        elif hasattr(obj, '__dict__'):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
        else:
            return obj

    def _emit_report_progress(self, stock_code: str, stock_name: str,
                              step: int, total: int, name: str, status: str):
        """发出 Report 阶段的进度事件"""
        from valuation_app.pipeline_runner import ProgressEvent
        self.runner.on_progress(ProgressEvent(
            stock_code=stock_code, stock_name=stock_name,
            stage="report", step=step, total_steps=total,
            step_name=name, status=status, elapsed_s=0,
        ))
