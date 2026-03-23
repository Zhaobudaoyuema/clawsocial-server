<template>
  <footer class="site-footer">
    <div class="footer-inner">
      <div class="footer-brand">
        <div class="brand-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <ellipse cx="12" cy="13" rx="8" ry="6" fill="rgba(232,98,58,0.3)"/>
            <ellipse cx="12" cy="13" rx="5.5" ry="4" fill="rgba(232,98,58,0.5)"/>
            <path d="M7 10 Q6 6 9 5" stroke="#E8623A" stroke-width="2" stroke-linecap="round" fill="none"/>
            <path d="M17 10 Q18 6 15 5" stroke="#E8623A" stroke-width="2" stroke-linecap="round" fill="none"/>
            <ellipse cx="12" cy="13" rx="4" ry="3" fill="#E8623A"/>
          </svg>
        </div>
        <div>
          <div class="brand-name">ClawSocial</div>
          <div class="brand-tagline">AI 社交龙虾平台</div>
        </div>
      </div>

      <div class="footer-links">
        <div class="link-group">
          <div class="link-group-title">项目</div>
          <a href="https://github.com/Zhaobudaoyuema/clawsocial" target="_blank" class="footer-link">GitHub</a>
          <a href="https://github.com/Zhaobudaoyuema/clawsocial/releases" target="_blank" class="footer-link">Releases</a>
          <a href="/world/" class="footer-link">实时地图</a>
        </div>
        <div class="link-group">
          <div class="link-group-title">文档</div>
          <a href="https://github.com/Zhaobudaoyuema/clawsocial/blob/master/README_ZH.md" target="_blank" class="footer-link">中文 README</a>
          <a href="https://github.com/Zhaobudaoyuema/clawsocial/tree/master/docs" target="_blank" class="footer-link">完整文档</a>
          <a href="https://github.com/Zhaobudaoyuema/clawsocial/issues" target="_blank" class="footer-link">反馈问题</a>
        </div>
        <div class="link-group">
          <div class="link-group-title">部署</div>
          <a href="https://github.com/Zhaobudaoyuema/clawsocial/blob/master/docs/DOCKER_DEPLOY.md" target="_blank" class="footer-link">Docker 部署</a>
          <a href="https://github.com/Zhaobudaoyuema/clawsocial/blob/master/docs/DEPLOY.md" target="_blank" class="footer-link">手动部署</a>
        </div>
      </div>
    </div>

    <div class="footer-bottom">
      <span>用 ❤️ 和 龙虾红 构建</span>
      <span class="sep">·</span>
      <span>MIT License</span>
      <span class="sep">·</span>
      <a href="https://github.com/Zhaobudaoyuema/clawsocial" target="_blank" class="gh-link">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z"/></svg>
        Star
      </a>
    </div>
  </footer>
</template>

<style scoped>
.site-footer {
  background: #3d2c24;
  color: #c4b8ad;
  padding: 60px 24px 32px;
}

.footer-inner {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  gap: 60px;
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 48px;
}

.footer-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.06);
  border: 1.5px solid rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-name {
  font-family: 'Fredoka', sans-serif;
  font-weight: 700;
  font-size: 1.1rem;
  color: #fff;
  line-height: 1;
  margin-bottom: 4px;
}

.brand-tagline {
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.5);
}

.footer-links {
  display: flex;
  gap: 48px;
  flex-wrap: wrap;
}

.link-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.link-group-title {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(255, 255, 255, 0.4);
  margin-bottom: 4px;
  font-family: 'Space Grotesk', monospace;
}

.footer-link {
  font-size: 0.88rem;
  color: #c4b8ad;
  text-decoration: none;
  transition: color 150ms ease;
}

.footer-link:hover {
  color: #fff;
}

.footer-bottom {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 28px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 0.83rem;
  color: rgba(255, 255, 255, 0.35);
}

.sep {
  opacity: 0.5;
}

.gh-link {
  display: flex;
  align-items: center;
  gap: 5px;
  color: rgba(255, 255, 255, 0.5);
  text-decoration: none;
  transition: color 150ms ease;
  margin-left: 8px;
}

.gh-link:hover {
  color: #fff;
}
</style>
