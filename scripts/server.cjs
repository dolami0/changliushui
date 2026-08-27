const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = process.env.DEPLOY_RUN_PORT || 5000;
const DIST_DIR = path.join(__dirname, '..', 'dist');

// 从环境变量读取 token（支持多种变量名）
const TOKEN = process.env.VITE_COZE_TOKEN || process.env.COZE_TOKEN || process.env.TOKEN || '';

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

const server = http.createServer((req, res) => {
  let filePath = path.join(DIST_DIR, req.url === '/' ? 'index.html' : req.url);

  // 处理 SPA 路由：如果文件不存在且不是静态资源，返回 index.html
  if (!fs.existsSync(filePath) && !req.url.startsWith('/assets/')) {
    filePath = path.join(DIST_DIR, 'index.html');
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('Not Found');
      return;
    }

    const ext = path.extname(filePath);
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    // 如果是 HTML，注入运行时环境变量
    if (ext === '.html') {
      let html = data.toString();
      const envScript = `<script>window.__ENV__ = { VITE_COZE_TOKEN: "${TOKEN}" };</script>`;
      // 在 </head> 前注入环境变量脚本
      html = html.replace('</head>', `${envScript}</head>`);
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(html);
    } else {
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(data);
    }
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Server running at http://0.0.0.0:${PORT}/`);
  console.log(`Token loaded: ${TOKEN ? 'yes (length: ' + TOKEN.length + ')' : 'no'}`);
});
