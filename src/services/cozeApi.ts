/* ------------------------------------------------------------------ */
/*  Coze 通用数据服务层 — 五大古籍分类                                 */
/* ------------------------------------------------------------------ */

const COZE_BASE = 'https://api.coze.cn/v1/databases';
const TOKEN = import.meta.env.VITE_COZE_TOKEN || '';

// ====== 数据库 ID 常量 ======
const DB_CANGJING  = '7611455655748304896'; // 藏经阁
const DB_TIANJIJUAN = '7479116110479048754'; // 天机卷
const DB_TRACKING   = '7645332166129287218'; // 追踪令
const DB_LINGGUANG  = '7645332554400153646'; // 灵光
const DB_CASES      = '7645333715039830079'; // 案例
const DB_WANYEPU   = '7639784337973477386'; // 万业谱
const DB_DINGSHULU  = '7640094415800860724'; // 定数录
const DB_YINGUOBU   = '7640928034144698374'; // 因果簿
const DB_REPORTS_V6 = '7644911309938589711'; // 估值报告V6（按Agent拆分存储）
