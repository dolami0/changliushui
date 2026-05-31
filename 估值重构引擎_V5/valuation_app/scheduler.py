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
        self.detail_db_id = config.get("detail_database_id", "")
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
                    write_ok = False
                    ts = datetime.now().strftime("%Y%m%d_%H%M")
                    if self.output_db_id:
                        try:
                            ts = self._write_result_to_coze_v5(rec, result, deepseek_key)
                            write_ok = True
                        except Exception as e:
                            ts = datetime.now().strftime("%Y%m%d_%H%M")
                            logger.error(f"写入输出表失败: {e}")
                    record_id = rec.get("id", "")
                    if record_id and write_ok:
                        self.coze.mark_record_complete(self.agent0_db_id, record_id)
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
    # V6 直接写入 (去掉 V5→V4 compat，直接从 result 取数据)
    # ═══════════════════════════════════════

    @staticmethod
    def _get_core_v6(result: dict) -> dict:
        """从 V6 result 提取核心财务字段。"""
        a1 = result.get("agent1", {})
        if not isinstance(a1, dict):
            return {}
        # packages.core.fields (标准 Agent-1 输出)
        pkgs = a1.get("packages", {}) if isinstance(a1.get("packages"), dict) else {}
        core = pkgs.get("core", {}) if isinstance(pkgs, dict) else {}
        fields = core.get("fields", {}) if isinstance(core, dict) else {}
        if fields:
            return fields
        # clean_financials (旧格式兜底)
        cf = a1.get("clean_financials", {})
        return cf if isinstance(cf, dict) else {}

    @staticmethod
    def _get_routing_v6(result: dict) -> dict:
        """从 V6 result 提取路由判决。优先 agent2.routing_decision。"""
        a2 = result.get("agent2", {})
        if isinstance(a2, dict):
            rd = a2.get("routing_decision", {})
            if isinstance(rd, dict) and rd:
                return rd
        # 兜底: agent3.valuation_routing
        a3 = result.get("agent3", {})
        if isinstance(a3, dict):
            vr = a3.get("valuation_routing", {})
            if isinstance(vr, dict) and vr:
                return vr
        return {}

    def _write_result_to_coze_v5(self, agent0_record: dict, result: dict, deepseek_key: str):
        """V6 版本：直接从 result 取数据写入 Coze + 保存 JSON。"""
        from valuation_app.report_builder import build_markdown_report, save_report

        stock_code = agent0_record.get("stock_code", "")
        stock_name = agent0_record.get("stock_name", "")
        ts = datetime.now().strftime("%Y%m%d_%H%M")

        # ── rNPV 管线键名映射 (agent3r→agent3, agent2r→agent2) ──
        pipeline_type = result.get("pipeline_type", "standard")
        # 先保存 rNPV 专属数据（在键名映射前）
        _rnpv_data = {}
        if pipeline_type == "rnpv":
            for rnpv_key in ("agent1r", "agent2r", "agent3r"):
                val = result.get(rnpv_key)
                if val is not None:
                    _rnpv_data[rnpv_key] = val
            if "agent3" not in result and "agent3r" in result:
                result = dict(result)
                result["agent3"] = result.pop("agent3r")
            if "agent2" not in result and "agent2r" in result:
                result = dict(result)
                result["agent2"] = result.pop("agent2r")
            # rNPV 输出格式归一化: probability_weighted → valuation_summary
            a3 = result.get("agent3", {})
            if isinstance(a3, dict) and "valuation_summary" not in a3:
                pw = a3.get("probability_weighted", {})
                if pw:
                    a3 = dict(a3)
                    a3["valuation_summary"] = {
                        "probability_weighted_upside_pct": pw.get("weighted_upside_pct", 0),
                        "asymmetry_ratio": pw.get("asymmetry_ratio", 0),
                    }
                    result["agent3"] = a3
            # rNPV scenarios格式归一化: scenario_valuation dict → scenarios list
            sv = a3.get("scenario_valuation", {})
            if isinstance(sv, dict) and not a3.get("scenarios"):
                a3["scenarios"] = [
                    {"name": sn, "probability_pct": round(d.get("probability", 0) * 100, 1),
                     "upside_pct": d.get("upside_pct", 0),
                     "target_mcap_yi": d.get("total_value_yi", 0)}
                    for sn in ("bear", "base", "bull")
                    for d in [sv.get(sn, {})]
                ]
                result["agent3"] = a3

            # rNPV 没有标准 routing_decision，从 agent2r 的 routing 字段提取
            if "routing_decision" not in result:
                a2r = result.get("agent2", {})
                if isinstance(a2r, dict):
                    rd = a2r.get("routing_decision", a2r.get("routing", {}))
                    if rd:
                        result["routing_decision"] = rd

        # ── 直接取 V6 数据（不经过 compat 转换）──
        core = self._get_core_v6(result)
        routing = self._get_routing_v6(result)
        a3 = result.get("agent3", {}) if isinstance(result.get("agent3"), dict) else {}
        a1_raw = result.get("agent1", {}) if isinstance(result.get("agent1"), dict) else {}
        fw = a1_raw.get("forward_looking", {}) if isinstance(a1_raw.get("forward_looking"), dict) else {}
        vs = a3.get("valuation_summary", {}) if isinstance(a3.get("valuation_summary"), dict) else {}
        conf = a3.get("confidence", {}) if isinstance(a3.get("confidence"), dict) else {}
        ta = a3.get("trade_annotation", {}) if isinstance(a3.get("trade_annotation"), dict) else {}
        scenarios = a3.get("scenarios", []) if isinstance(a3.get("scenarios"), list) else []

        bear = next((s for s in scenarios if isinstance(s, dict) and "bear" in str(s.get("name", "")).lower()), {})
        base = next((s for s in scenarios if isinstance(s, dict) and "base" in str(s.get("name", "")).lower()), {})
        bull = next((s for s in scenarios if isinstance(s, dict) and "bull" in str(s.get("name", "")).lower()), {})

        # ── 保存完整结构化 JSON（最优先，不依赖任何额外处理）──
        data_dir = Path(__file__).resolve().parent.parent / "reports" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        json_path = data_dir / f"{stock_code}_{ts}.json"
        a2_raw = result.get("agent2", {}) if isinstance(result.get("agent2"), dict) else {}
        rd_raw_val = a2_raw.get("routing_decision", {}) if isinstance(a2_raw.get("routing_decision"), dict) else {}
        a2a_raw = result.get("agent2a", {}) if isinstance(result.get("agent2a"), dict) else {}

        payload = {
            "agent0": agent0_record,
            "agent1": self._serialize_agent_output(a1_raw),
            "agent2": self._serialize_agent_output(a2_raw),
            "agent2a": self._serialize_agent_output(a2a_raw) if a2a_raw else {},
            "agent3": self._serialize_agent_output(a3),
            "routing_decision": rd_raw_val,
            "pipeline_version": result.get("pipeline_version", "6.0"),
            "pipeline_type": pipeline_type,
            "audit": result.get("audit", {}),
        }
        # rNPV 管线保留专属数据（从映射前保存的 _rnpv_data 取）
        if pipeline_type == "rnpv" and _rnpv_data:
            for rnpv_key, rnpv_val in _rnpv_data.items():
                payload[rnpv_key] = self._serialize_agent_output(rnpv_val)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

        # ── 生成 Markdown 报告（可选，失败不影响主流程）──
        report_path = ""
        try:
            a1_for_report = {
                "clean_financials": core,
                "valuation_anchor": {"pe_ttm": core.get("pe_ttm", 0), "pb": core.get("pb", 0),
                                     "valuation_model": routing.get("primary_model", "")},
                "valuation_routing": routing,
                "market_sanity": a3.get("market_sanity", {}),
                "forward_looking": fw,
            }
            a2_for_report = {
                "dcf_results": {"valuation_approach": routing.get("primary_model", ""),
                                "scenario_details": a3.get("scenario_valuation", {}).get("scenario_details", {})}
            }
            md = build_markdown_report(agent0_record, a1_for_report, a2_for_report, a3, a2a_raw)
            report_path = save_report(md, stock_code, ts=ts) or ""
        except Exception as e:
            logger.warning(f"Markdown报告跳过: {e}")

        # ── 写入 Coze 输出表 ──
        row = {
            "stock_code": stock_code, "stock_name": stock_name,
            "event_date": agent0_record.get("bstudio_create_time", ""),
            "event_source": agent0_record.get("event_source", ""),
            "primary_model": routing.get("primary_model", ""),
            "prob_weighted_upside_pct": str(vs.get("probability_weighted_upside_pct", "")),
            "asymmetry_ratio": str(vs.get("asymmetry_ratio", "")),
            "quality_flag": vs.get("quality_flag", ""),
            "current_mcap_billion": str(core.get("market_cap_yi", "")),
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
        self.coze.insert_records(self.output_db_id, [row])

        # ── 写入详情归档表（完整JSON，供深度回溯）──
        if self.detail_db_id:
            try:
                _write_detail_row(self.detail_db_id, self.coze, agent0_record,
                                  a1_raw, a2_raw, a2a_raw, a3, routing,
                                  pipeline_type, _rnpv_data, stock_code, stock_name, ts)
            except Exception as e:
                logger.warning(f"[V6] 详情归档写入失败(非致命): {e}")

        # ── 评测记录（可选，失败不影响主流程）──
        try:
            from evals.eval_builder import build_eval_record
            eval_id = build_eval_record(agent0_record, result, {"clean_financials": core})
            logger.info(f"[Eval] 评测记录已保存: {eval_id}")
        except Exception as e:
            logger.warning(f"[Eval] 评测记录跳过: {e}")

        logger.info(f"[V6] 写入完成: {stock_code} ts={ts}")
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


# ── 详情归档写入（模块级函数，供 _write_result_to_coze_v5 调用）──

def _write_detail_row(detail_db_id: str, coze, agent0_record: dict,
                      a1_raw: dict, a2_raw: dict, a2a_raw: dict,
                      a3: dict, routing: dict,
                      pipeline_type: str, _rnpv_data: dict,
                      stock_code: str, stock_name: str, ts: str):
    """将完整 Agent JSON 归档写入 Coze 详情表 7644911309938589711。

    与输出表（摘要字段）互补：此表存每个 Agent 的完整原始输出，供深度回溯。
    """
    serialize = Scheduler._serialize_agent_output

    # ── 按管线类型选择正确的数据源 ──
    if pipeline_type == "rnpv":
        # rNPV：使用专属三步管线数据，而非标准 Agent-1/2/3
        agent1_detail = _rnpv_data.get("agent1r", a1_raw)
        agent2_detail = _rnpv_data.get("agent2r", a2_raw)
        agent3_detail = _rnpv_data.get("agent3r", a3)
        agent2a_detail = {}
        routing_detail = {"primary_model": "F", "pipeline_type": "rnpv",
                          "note": "rNPV无标准模型路由，F为管线估值锚定"}
    elif pipeline_type == "sotp":
        # SOTP：使用标准 Agent-1 + Agent-2a + Agent-3s
        agent1_detail = a1_raw
        agent2_detail = a2_raw
        agent3_detail = a3
        agent2a_detail = a2a_raw
        routing_detail = routing
    else:
        # 标准管线
        agent1_detail = a1_raw
        agent2_detail = a2_raw
        agent3_detail = a3
        agent2a_detail = a2a_raw
        routing_detail = routing

    # 注意: Coze insert_records 会自动将所有值转为字符串
    # json.dumps 确保嵌套结构在 Coze 中以 JSON 字符串形式存储
    # 注意: 不要传 bstudio_create_time 等 bstudio_* 字段，
    # Coze 表会自动注入这些系统字段，手动传递会导致 "Column specified twice" 错误
    detail_row = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "event_date": agent0_record.get("bstudio_create_time", ""),
        "json_filename": f"{stock_code}_{ts}",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "agent0_json": json.dumps(serialize(agent0_record), ensure_ascii=False, default=str),
        "agent1_json": json.dumps(serialize(agent1_detail), ensure_ascii=False, default=str),
        "agent2_json": json.dumps(serialize(agent2_detail), ensure_ascii=False, default=str),
        "agent2a_json": json.dumps(serialize(agent2a_detail), ensure_ascii=False, default=str) if agent2a_detail else "",
        "agent3_json": json.dumps(serialize(agent3_detail), ensure_ascii=False, default=str),
        "routing_json": json.dumps(serialize(routing_detail), ensure_ascii=False, default=str),
    }
    coze.insert_records(detail_db_id, [detail_row])
    logger.info(f"[V6] 详情归档写入完成: {stock_code} → {detail_db_id}")
