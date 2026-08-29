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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
# 兜底: 确保异常日志写入文件, 防止静默崩溃
_log_file = Path(__file__).resolve().parent.parent / "scheduler.log"
_handler = logging.FileHandler(str(_log_file), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
# 同时输出到 stderr (uvicorn 会捕获)
_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setFormatter(logging.Formatter("[SCHEDULER %(levelname)s] %(message)s"))
logger.addHandler(_stderr_handler)


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
        # 单条管线超时: 默认取轮询间隔的80%或3600s中更小的, 既给足时间又保证下一轮不会被阻塞超过一轮
        _cfg_timeout = config.get("record_timeout_sec", 0)
        self._record_timeout = _cfg_timeout if _cfg_timeout > 0 else min(3600, int(self.interval * 0.8))
        self._task: asyncio.Task | None = None
        self._running = False
        self._completed_ids: set[str] = set()  # 同session内已标记的记录，防Coze API失败导致重复处理
        self.last_poll_at: str | None = None
        self.next_poll_at: str | None = None
        # 运行时状态（供 dashboard 查询）
        self.active_jobs: list[dict] = []
        self.completed_jobs: list[dict] = []
        self.current_poll_status: str = "idle"
        self._polling: bool = False
        self._latest_review: dict | None = None  # 最新一轮审阅结果
        self._fail_tracker: dict[str, int] = {}    # {record_id: 连续失败次数} 防止无限重试
        self._fail_tracker_date: str = ""           # 重置日期（跨天清零）

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
        """主循环：每整点轮询 (北京时间)，高峰时段跳过（DeepSeek 峰谷定价避峰）"""
        await asyncio.sleep(3)
        from valuation_app.offpeak import is_peak_bj, seconds_until_offpeak
        while self._running:
            next_hour = self._next_hour_local()
            now_utc = datetime.now(timezone.utc)
            wait_sec = max(10, (next_hour - now_utc).total_seconds())
            # 高峰时段（北京 9:00-12:00 / 14:00-18:00）不执行，顺延到空闲时段
            if is_peak_bj(next_hour):
                extra = seconds_until_offpeak(next_hour)
                wait_sec += extra
                next_hour = next_hour + timedelta(seconds=extra)
                logger.info(f"高峰时段避峰，顺延至 {next_hour.isoformat()} (额外等待 {extra:.0f}s)")
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
        if self._polling:
            logger.info("上一轮轮询尚未完成，跳过本次")
            return []
        self._polling = True
        self.current_poll_status = "polling"
        self.last_poll_at = datetime.now(timezone.utc).isoformat()
        try:
            return await asyncio.to_thread(self._poll_sync)
        except Exception:
            self._polling = False
            self.current_poll_status = "idle"
            raise

    def _poll_sync(self) -> list[dict]:
        try:
            return self._poll_sync_inner()
        finally:
            self._polling = False
            self.current_poll_status = "idle"
            self.active_jobs = []

    def _poll_sync_inner(self) -> list[dict]:
        # 1. 查询未完成记录
        records = self.coze.query_incomplete_records(self.agent0_db_id)
        if not records:
            logger.info("本轮无待处理记录")
            return []

        # 2. (stock_code, event_date) 去重: 同股同日保留最新一条, 其余直接标记完成
        by_key: dict[tuple, list[dict]] = {}
        deduped_strays: list[dict] = []  # stock_code 为空的记录, 后续脏检查处理
        for r in records:
            code = (r.get("stock_code", "") or "").strip()
            if not code:
                deduped_strays.append(r)
                continue
            evt_date = (
                r.get("bstudio_create_time", "") or r.get("event_date", "") or r.get("created_at", "")
            ).strip()[:10]
            key = (code, evt_date)
            by_key.setdefault(key, []).append(r)
        deduped = []
        for (code, evt_date), recs in by_key.items():
            recs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            deduped.append(recs[0])
            for stale in recs[1:]:
                sid = stale.get("id", "")
                logger.info(f"[DEDUP] 同股同日重复, 跳过: stock={code} date={evt_date} id={sid}")
                try:
                    self.coze.mark_record_complete(self.agent0_db_id, sid)
                except Exception as e:
                    logger.error(f"[DEDUP] 标记重复记录失败: stock={code} id={sid} — {e}")
        records = deduped + deduped_strays

        logger.info(f"待处理: {len(records)} 条 (原始 {len(by_key)} 个(stock_code,event_date)组合)")
        self.active_jobs = [{"stock_code": r.get("stock_code", "?"),
                             "stock_name": r.get("stock_name", "?"),
                             "status": "queued"} for r in records]

        # 3. 获取 DeepSeek API Key
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

            # 关键语料缺失检查：预研管线某节点静默失败会留下空语料，
            # 这种记录进估值引擎产出的报告作废。检测到缺失→不走估值，
            # 复用 PreScreen 回写通道标注"语料缺失"，大屏可见。
            CORPUS_FIELDS = {
                "investment_theme": "投资主题",
                "industry_expert_research": "产业链研究",
                "adversarial_thinking": "逆向推演",
                "event_deduction": "事件推演",
                "future": "催化日历",
            }
            missing = [cn for f, cn in CORPUS_FIELDS.items()
                       if not (rec.get(f, "") or "").strip()]
            if missing:
                record_id = rec.get("id", "")
                reason = f"语料缺失: {','.join(missing)}"
                logger.warning(f"[CorpusMissing] 拦截 {stock_code}({rec.get('stock_name','?')}): {reason}")
                if record_id:
                    try:
                        self.coze.update_records(
                            self.agent0_db_id,
                            [{"field_name": "pre_screen_score", "value": "0"},
                             {"field_name": "pre_screen_detail",
                              "value": json.dumps({"corpus_missing": missing, "cut_reason": reason},
                                                  ensure_ascii=False)[:15000]}],
                            {"logic": "and", "conditions": [{"left": "id", "operation": "equal", "right": record_id}]},
                        )
                        self.coze.mark_record_complete(self.agent0_db_id, record_id)
                    except Exception as e:
                        logger.error(f"[CorpusMissing] 回写失败: {stock_code} — {e}")
                continue

            # ── 同session去重 ──
            record_id = rec.get("id", "")
            if record_id and record_id in self._completed_ids:
                logger.info(f"[DEDUP] 跳过已处理记录: stock={stock_code} id={record_id}")
                continue

            job = {"stock_code": stock_code,
                   "stock_name": rec.get("stock_name", "?"),
                   "status": "running"}
            job_statuses.append(job)
            self.active_jobs = job_statuses

            record_id = rec.get("id", "")
            rec_timeout = getattr(self, '_record_timeout', 600)
            result = None

            # ── 超时保护: 单条记录最长 _record_timeout 秒 ──
            _exec = ThreadPoolExecutor(max_workers=1)
            try:
                _future = _exec.submit(self.runner.run_single, rec, deepseek_key)
                result = _future.result(timeout=rec_timeout)
            except FuturesTimeoutError:
                logger.error(f"处理 {rec.get('stock_code', '?')} 超时(>{rec_timeout}s)，强制中断")
                job["status"] = "error"
                results.append({"agent0": rec, "status": "error", "error": f"单记录超时(>{rec_timeout}s)"})
                self._handle_failure(rec)
                continue
            except Exception as e:
                logger.error(f"处理 {rec.get('stock_code', '?')} 失败: {e}")
                job["status"] = "error"
                results.append({"agent0": rec, "status": "error", "error": str(e)})
                self._handle_failure(rec)
                continue
            finally:
                _exec.shutdown(wait=False)  # 不等待卡死线程

            # ── 管线成功，处理结果 ──
            results.append(result)

            if result.get("status") == "pre_screened_out":
                job["status"] = "pre_screened_out"
                stock_code = rec.get("stock_code", "")
                stock_name = rec.get("stock_name", "")
                pre_screen = result.get("pre_screen", {})
                record_id = rec.get("id", "")
                if record_id:
                    try:
                        self.coze.update_records(
                            self.agent0_db_id,
                            [{"field_name": "pre_screen_score", "value": str(pre_screen.get("total_score", 0))},
                             {"field_name": "pre_screen_detail", "value": json.dumps(pre_screen, ensure_ascii=False, default=str)[:15000]}],
                            {"logic": "and", "conditions": [{"left": "id", "operation": "equal", "right": record_id}]},
                        )
                        self.coze.mark_record_complete(self.agent0_db_id, record_id)
                        logger.info(f"[PreScreen] BLOCK {stock_code}({stock_name}): 总分{pre_screen.get('total_score','?')}/40 — {pre_screen.get('cut_reason','?')[:100]}")
                    except Exception as e:
                        logger.error(f"[PreScreen] 写入源表失败: {rec.get('stock_code')} — {e}")
                continue

            if result.get("status") == "done":
                stock_code = rec.get("stock_code", "")
                stock_name = rec.get("stock_name", "")
                self._emit_report_progress(stock_code, stock_name, 1, 2, "写入Coze输出表", "running")
                ts = datetime.now().strftime("%Y%m%d_%H%M")
                if self.output_db_id:
                    try:
                        ts = self._write_result_to_coze_v5(rec, result, deepseek_key)
                    except Exception as e:
                        ts = datetime.now().strftime("%Y%m%d_%H%M")
                        logger.error(f"写入输出表失败: {e}")
                self._emit_report_progress(stock_code, stock_name, 1, 2, "写入Coze输出表", "done")
                self._emit_report_progress(stock_code, stock_name, 2, 2, "构建Markdown报告", "running")
                self._emit_report_progress(stock_code, stock_name, 2, 2, "构建Markdown报告", "done")
                job["status"] = "done"
                report_url = f"http://localhost:{self.server_port}/report/{stock_code}_{ts}"
                self.completed_jobs.append({
                    "stock_code": stock_code, "stock_name": stock_name, "status": "done",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "report_url": report_url,
                    "upside_pct": result.get("agent3", {}).get("valuation_summary", {}).get("probability_weighted_upside_pct", 0),
                })
                self._ensure_complete(rec, record_id)
            else:
                job["status"] = "error"
                logger.error(f"管线处理失败: {rec.get('stock_code')} — {result.get('error','未知错误')[:120]}")
                # 完整 traceback 单独存文件，便于排查 errno 22 等异常根因
                _tb = result.get('traceback', '')
                if _tb:
                    try:
                        _err_dir = Path(__file__).resolve().parent.parent / "reports" / "errors"
                        _err_dir.mkdir(parents=True, exist_ok=True)
                        _err_file = _err_dir / f"{rec.get('stock_code','unknown')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                        _err_file.write_text(
                            f"stock: {rec.get('stock_code')} {rec.get('stock_name')}\n"
                            f"record_id: {rec.get('id')}\n"
                            f"error: {result.get('error','')}\n"
                            f"--- traceback ---\n{_tb}",
                            encoding="utf-8"
                        )
                        logger.error(f"  → traceback已存: {_err_file.name}")
                    except Exception as _e:
                        logger.warning(f"  traceback写入失败: {_e}")
                self._handle_failure(rec)

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
    # 去重辅助
    # ═══════════════════════════════════════

    def _ensure_complete(self, rec: dict, record_id: str):
        """管线成功 → 确保 Coze 侧 is_complete=true"""
        if not record_id:
            return
        if record_id in self._completed_ids:
            return
        try:
            self.coze.mark_record_complete(self.agent0_db_id, record_id)
            self._completed_ids.add(record_id)
        except Exception as e:
            logger.error(f"[MARK] 补标失败(不影响结果): stock={rec.get('stock_code','?')} — {e}")

    def _handle_failure(self, rec: dict):
        """管线失败 → 按重试上限决定是否强制标记完成"""
        rid = rec.get("id", "")
        if not rid:
            return
        if self._fail_tracker_date != datetime.now().strftime("%Y%m%d"):
            self._fail_tracker.clear()
            self._fail_tracker_date = datetime.now().strftime("%Y%m%d")
        fails = self._fail_tracker.get(rid, 0) + 1
        self._fail_tracker[rid] = fails
        if fails >= 2:
            logger.warning(f"记录 {rid}({rec.get('stock_code')}) 连续失败{fails}次，强制标记完成")
            try:
                self.coze.mark_record_complete(self.agent0_db_id, rid)
                self._completed_ids.add(rid)
            except Exception as e:
                logger.error(f"强制标记也失败: {rec.get('stock_code')} — {e}")
        else:
            logger.info(f"记录 {rid} 失败 {fails}/2 次，退回 is_complete=false 等待重试")
            try:
                self.coze.update_records(
                    self.agent0_db_id,
                    [{"field_name": "is_complete", "value": "false"}],
                    {"logic": "and", "conditions": [
                        {"left": "id", "operation": "equal", "right": rid}
                    ]},
                )
            except Exception as e:
                logger.error(f"退回is_complete失败: {e}")

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
            # 多路径提取 stock_code / stock_name（V5 V4 V7 格式兼容）
            a0 = r.get("event_meta", {}) or r.get("agent0", {})
            a1 = r.get("agent1", {})
            audit = r.get("audit", {})
            code = a1.get("stock_code", "") or a0.get("stock_code", "") or audit.get("stock_code", "?")
            name = (
                a0.get("stock_name", "")
                or audit.get("stock_name", "")
                or a1.get("packages", {}).get("core", {}).get("fields", {}).get("stock_name", "")
                or a1.get("clean_financials", {}).get("stock_name", "")
                or code
            )
            upside = vs.get("probability_weighted_upside_pct", 0)
            asym = vs.get("asymmetry_ratio", 0)
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
            lines.append(f"- 加权涨幅: {upside:+.1f}% | 不对称比: {asym:.1f}x")
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
        # 先保存 rNPV 专属数据（V7: 保留 agent1r 原始数据供 detail 表使用）
        _rnpv_data = {}
        if pipeline_type == "rnpv":
            # agent1r/agent2r 直接取（V7: agent2r 已是 Agent-3 兼容格式, agent2/agent3 = agent2r）
            for rnpv_key in ("agent1r", "agent2r"):
                val = result.get(rnpv_key)
                if val is not None:
                    _rnpv_data[rnpv_key] = val
            # V7: orchestrator 已注入 agent2/agent3/agent2a/routing_decision, 无需额外归一化

        # ── 直接取 V6 数据（不经过 compat 转换）──
        core = self._get_core_v6(result)
        routing = self._get_routing_v6(result)
        a3 = result.get("agent3", {}) if isinstance(result.get("agent3"), dict) else {}
        a1_raw = result.get("agent1", {}) if isinstance(result.get("agent1"), dict) else {}
        fw = a1_raw.get("forward_looking", {}) if isinstance(a1_raw.get("forward_looking"), dict) else {}
        vs = a3.get("valuation_summary", {}) if isinstance(a3.get("valuation_summary"), dict) else {}
        conf = a3.get("confidence", {}) if isinstance(a3.get("confidence"), dict) else {}
        ta = a3.get("trade_annotation", {}) if isinstance(a3.get("trade_annotation"), dict) else {}
        scenario_details = a3.get("scenario_valuation", {}).get("scenario_details", {})
        if not isinstance(scenario_details, dict):
            scenario_details = {}

        # 归一化: scenario_valuation dict → scenarios list（标准+ rNPV 通用）
        # LLM 输出 probability 为 0-1 小数，转为 probability_pct; upside_pct 缺时从 target_mcap 兜底计算
        scenarios = []
        for sn in ("bear", "base", "bull"):
            raw = scenario_details.get(sn)
            if not isinstance(raw, dict):
                raw = {}
            # 以原始 LLM 产出为底（含所有锚参数），再覆盖汇总字段
            d = dict(raw)
            up = d.get("upside_pct")
            if up is None:
                tgt = d.get("target_mcap_yi") or d.get("total_value_yi", 0)
                mcap = core.get("market_cap_yi", 0)
                if tgt and mcap:
                    try:
                        up = round((float(tgt) / float(mcap) - 1) * 100, 1)
                    except (ValueError, ZeroDivisionError):
                        up = 0
                else:
                    up = 0
            d["name"] = sn
            d["probability_pct"] = round(d.get("probability", 0) * 100, 1)
            d["upside_pct"] = up
            d.pop("probability", None)  # 清理原始0-1字段，避免混淆
            scenarios.append(d)
        a3["scenarios"] = scenarios
        result["agent3"] = a3

        bear = scenarios[0]
        base = scenarios[1]
        bull = scenarios[2]

        # ── 保存完整结构化 JSON（最优先，不依赖任何额外处理）──
        data_dir = Path(__file__).resolve().parent.parent / "reports" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        json_path = data_dir / f"{stock_code}_{ts}.json"
        a2_raw = result.get("agent2", {}) if isinstance(result.get("agent2"), dict) else {}
        rd_raw_val = a2_raw.get("routing_decision", {}) if isinstance(a2_raw.get("routing_decision"), dict) else {}
        a2a_raw = result.get("agent2a", {}) if isinstance(result.get("agent2a"), dict) else {}

        baseline_report = result.get("baseline_report", "")

        payload = {
            "baseline_report": baseline_report,
            "event_meta": {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "raw_event_text": agent0_record.get("raw_event_text", ""),
                "investment_theme": agent0_record.get("investment_theme", ""),
                "industry_expert_research": agent0_record.get("industry_expert_research", ""),
                "adversarial_thinking": agent0_record.get("adversarial_thinking", ""),
                "event_deduction": agent0_record.get("event_deduction", ""),
                "future": agent0_record.get("future", ""),
                "knowledge_supplement": agent0_record.get("knowledge_supplement", ""),
                "preliminary_reasoning": agent0_record.get("preliminary_reasoning", ""),
                "event_source": agent0_record.get("event_source", ""),
                "response_level": agent0_record.get("response_level", ""),
                "created_at": agent0_record.get("created_at", ""),
                "bstudio_create_time": agent0_record.get("bstudio_create_time", ""),
            },
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
                _write_detail_row(self.detail_db_id, self.coze, agent0_record, baseline_report,
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

def _write_detail_row(detail_db_id: str, coze, agent0_record: dict, baseline_report: str,
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
        # V7: agent2r 已是 Agent-3 兼容格式, agent3=agent2r
        # agent3r 不再存在（已合并入 agent2r）
        agent1_detail = _rnpv_data.get("agent1r", a1_raw)
        agent2_detail = a2_raw                      # agent2 = agent2r (Agent-3 兼容)
        agent3_detail = a3                          # agent3 = agent2r (Agent-3 兼容)
        agent2a_detail = a2a_raw                    # V7 修复: 不再为空
        routing_detail = routing                    # V7 修复: 使用实际路由
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
        "json_filename": f"{stock_code}_{ts}",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "agent0_json": json.dumps(serialize(agent0_record), ensure_ascii=False, default=str),  # V5/V6 兼容
        "baseline_report": baseline_report,                                                    # V7 投资地图
        "agent1_json": json.dumps(serialize(agent1_detail), ensure_ascii=False, default=str),
        "agent2_json": json.dumps(serialize(agent2_detail), ensure_ascii=False, default=str),
        "agent2a_json": json.dumps(serialize(agent2a_detail), ensure_ascii=False, default=str) if agent2a_detail else "",
        "agent3_json": json.dumps(serialize(agent3_detail), ensure_ascii=False, default=str),
        "routing_json": json.dumps(serialize(routing_detail), ensure_ascii=False, default=str),
    }
    coze.insert_records(detail_db_id, [detail_row])
    logger.info(f"[V6] 详情归档写入完成: {stock_code} → {detail_db_id}")
