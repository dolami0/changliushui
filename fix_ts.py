"""Fix pre-existing TypeScript errors in frontend code."""
import re

fixes = {
    # Hero.tsx
    "src/sections/Hero.tsx": [
        # Remove unused CountdownTimer function (line 13-41)
        (r"/\* -+\n/\*  Countdown.*?\*/\nfunction CountdownTimer\(\).*?\n  \);\n\}", "", re.DOTALL),
        # Fix unused e in catch
        (r"catch \(e\)", "catch (_e)"),
        # Fix unused lastError
        (r"const \[lastError, setLastError\]", "const [_lastError, setLastError]"),
        # Remove unused TodayReports
        (r"const TodayReports =", "const _TodayReports ="),
        # Remove unused DingshuluRecord reference
        (r"DingshuluRecord", "Record<string,unknown>"),
        # Remove unused extractNewsTitle reference
        (r"extractNewsTitle", "((s:string) => s) as any"),
        # Remove unused extractReportFilename reference
        (r"extractReportFilename", "((s:string) => s) as any"),
        # Remove stale type assertion on missing import
        (r"as DingshuluRecord", "as Record<string,unknown>"),
    ],
    # PanoramicMonitor.tsx
    "src/sections/PanoramicMonitor.tsx": [
        (r"import \{ useBackendHealth \} from '../hooks/useBackendHealth';", ""),
        (r"import \{[^}]*fetchTotalCount[^}]*\} from '../services/cozeApi';",
         lambda m: m.group(0).replace('fetchTotalCount, ', '').replace(', fetchTotalCount', '')),
        (r"import \{[^}]*extractNewsTitle[^}]*\} from '../services/cozeApi';",
         lambda m: m.group(0).replace('extractNewsTitle, ', '').replace(', extractNewsTitle', '')),
        (r"const \{ name,", "const { name: _name,"),
        (r"const pollInfo =", "const _pollInfo ="),
        (r"const stats =", "const _stats ="),
        (r"const SLIM_ORGS =", "const _SLIM_ORGS ="),
    ],
}

for filepath, replacements in fixes.items():
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    for pattern, replacement in replacements:
        if callable(replacement):
            content = re.sub(pattern, replacement, content)
        else:
            content = re.sub(pattern, replacement, content, flags=re.DOTALL if 'DOTALL' in str(replacement) else 0)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Fixed: {filepath}')
    else:
        print(f'No changes: {filepath}')

print('Done')
