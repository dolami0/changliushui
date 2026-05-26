"""
清洁打包脚本 — 只复制必须文件，排除多余内容
输出: D:\长流水_清洁版\
"""
import shutil, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SRC_FRONTEND = r"D:\长流水"
SRC_ENGINE = r"D:\长流水\估值重构引擎_V5"
DST = r"D:\长流水_清洁版"

def copy_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        return True
    return False

def copy_tree(src_dir, dst_dir):
    """复制整个目录树"""
    if os.path.isdir(src_dir):
        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir)
        shutil.copytree(src_dir, dst_dir, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        return True
    return False

def ensure_dir(dst_dir):
    os.makedirs(dst_dir, exist_ok=True)

copied = []
skipped = []

# ═══════════════════════════════════════
# 1. 根级 README (迁移指南)
# ═══════════════════════════════════════
guide = os.path.join(SRC_FRONTEND, "PROJECT_MIGRATION_GUIDE.md")
if os.path.exists(guide):
    copy_file(guide, os.path.join(DST, "README.md"))
    copied.append("README.md (迁移指南)")

# ═══════════════════════════════════════
# 2. 前端项目 → frontend/
# ═══════════════════════════════════════
F = os.path.join(DST, "frontend")

# 配置文件
for f in ["package.json", "package-lock.json", "vite.config.ts",
          "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json",
          "postcss.config.js", "tailwind.config.js", "eslint.config.js",
          ".gitignore", "index.html", "README.md"]:
    if copy_file(os.path.join(SRC_FRONTEND, f), os.path.join(F, f)):
        copied.append(f"frontend/{f}")

# src/ 全部源码
if copy_tree(os.path.join(SRC_FRONTEND, "src"), os.path.join(F, "src")):
    copied.append("frontend/src/ (全部源码)")

# public/ 全部静态资源
if copy_tree(os.path.join(SRC_FRONTEND, "public"), os.path.join(F, "public")):
    copied.append("frontend/public/ (图片/视频/案例JSON)")

# ═══════════════════════════════════════
# 3. 后端引擎 → engine/
# ═══════════════════════════════════════
E = os.path.join(DST, "engine")

# 根级文件
for f in ["requirements.txt", "package.json", "package-lock.json"]:
    if copy_file(os.path.join(SRC_ENGINE, f), os.path.join(E, f)):
        copied.append(f"engine/{f}")

# valuation_app/ (保留 README)
for f in ["server.py", "main.py", "coze_client.py", "pipeline_runner.py",
          "scheduler.py", "report_builder.py", "create_output_table.py",
          "config.json", "README.md"]:
    if copy_file(os.path.join(SRC_ENGINE, "valuation_app", f),
                 os.path.join(E, "valuation_app", f)):
        copied.append(f"engine/valuation_app/{f}")
# templates
if copy_tree(os.path.join(SRC_ENGINE, "valuation_app", "templates"),
             os.path.join(E, "valuation_app", "templates")):
    copied.append("engine/valuation_app/templates/")

# src/ (核心引擎 agents)
for f in ["data_fetcher.py", "agent1_data_anchor.py", "agent2_event_scenario.py", "agent3_report.py"]:
    if copy_file(os.path.join(SRC_ENGINE, "src", f), os.path.join(E, "src", f)):
        copied.append(f"engine/src/{f}")

# config/
if copy_file(os.path.join(SRC_ENGINE, "config", "endpoint_mapping.yaml"),
             os.path.join(E, "config", "endpoint_mapping.yaml")):
    copied.append("engine/config/endpoint_mapping.yaml")

# evals/ 案例库 (保留 JSON/MD/TS, 跳过 .js 脚本)
eval_src = os.path.join(SRC_ENGINE, "evals")
eval_dst = os.path.join(E, "evals")

# root evals files
for f in ["case_library_v2.json", "raw_news_eval_set.json"]:
    if copy_file(os.path.join(eval_src, f), os.path.join(eval_dst, f)):
        copied.append(f"engine/evals/{f}")

# evals/2.0/ — 只复制数据文件，跳过 .js 脚本
v2_src = os.path.join(eval_src, "2.0")
v2_dst = os.path.join(eval_dst, "2.0")
for f in os.listdir(v2_src):
    if f.endswith('.js'):
        skipped.append(f"engine/evals/2.0/{f} (构建脚本)")
        continue
    full_src = os.path.join(v2_src, f)
    full_dst = os.path.join(v2_dst, f)
    if os.path.isfile(full_src):
        copy_file(full_src, full_dst)
        copied.append(f"engine/evals/2.0/{f}")
    elif os.path.isdir(full_src):
        copy_tree(full_src, full_dst)
        copied.append(f"engine/evals/2.0/{f}/")

# reports/ 空输出目录
ensure_dir(os.path.join(E, "reports", "data"))
ensure_dir(os.path.join(E, "reports", "html"))
copied.append("engine/reports/data/ (空)")
copied.append("engine/reports/html/ (空)")

# node_modules/@investoday/ 只复制这个包
inv_src = os.path.join(SRC_ENGINE, "node_modules", "@investoday")
inv_dst = os.path.join(E, "node_modules", "@investoday")
if os.path.isdir(inv_src):
    if copy_tree(inv_src, inv_dst):
        copied.append("engine/node_modules/@investoday/ (数据API)")

# ═══════════════════════════════════════
# 4. 生成清单文件
# ═══════════════════════════════════════
manifest = f"""长流水 · 估值重构引擎 V5 — 清洁打包清单
打包时间: {__import__('datetime').datetime.now().isoformat()}

=== 目录结构 ===
长流水_清洁版/
├── README.md                启动指南
├── frontend/                前端项目 (React + Vite)
│   ├── index.html / package.json / vite.config.ts / ...
│   ├── src/                 全部源码 (76个文件)
│   └── public/              静态资源 (图片/视频/案例JSON)
└── engine/                  后端引擎 (Python + FastAPI)
    ├── requirements.txt / package.json
    ├── valuation_app/       FastAPI 服务 (9个文件)
    ├── src/                 核心引擎 (4个Agent)
    ├── config/              API端点映射
    ├── evals/               案例库 (JSON + MD + TS)
    ├── reports/             输出目录
    └── node_modules/@investoday/  数据API工具

=== 已排除的内容 ===
- node_modules/ (除 @investoday 外) → npm install 重新安装
- dist/ → npm run build 重新构建
- .agents/ / skills-lock.json → Claude Code IDE 文件
- docs/ → 历史设计文档
- .claude/ → IDE 本地设置
- __pycache__/ *.pyc → Python 缓存
- evals/2.0/*.js → 案例库构建脚本
- 有钱花.png → 已在 frontend/public/images/ 中

=== 已复制 {len(copied)} 项 ===
""" + "\n".join(f"  [OK] {c}" for c in copied)

if skipped:
    manifest += f"\n\n=== 已跳过 {len(skipped)} 项 ===\n" + "\n".join(f"  [SKIP] {s}" for s in skipped)

with open(os.path.join(DST, "MANIFEST.txt"), "w", encoding="utf-8") as f:
    f.write(manifest)

print(manifest)
print(f"\n打包完成! 输出: {DST}")
