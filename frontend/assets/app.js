(function () {
  const { pageTitles, defaultPage } = window.NovelConstants;

  const app = {
    state: { config: {}, paths: {}, platforms: {}, adProfiles: [] },
    currentPage: defaultPage,
    hasUserSelectedPage: false,
    api: null,
    logs: {
      process_novel: [],
      process_novel_batch: [],
      clean_text_ads: [],
      clean_text_breaks: [],
      novel_splitter: [],
      auto_publish: [],
      chapter_sync: [],
      web_crawler: [],
      character_material: [],
      current_plot: [],
      webnovel_writer: [],
    },
    logAliases: {},
    lastOutputs: {},
    lastBackups: {},
    taskStatus: {},
    progressState: {},
    taskStore: window.NovelTaskStateStore ? window.NovelTaskStateStore.create() : null,
    activeResultModes: {},
    resultTexts: {},
    saveTimer: null,
    statusOnlyPages: ['auto_publish', 'chapter_sync', 'web_crawler', 'webnovel_writer'],
    loglessPages: ['auto_publish', 'chapter_sync', 'novel_splitter', 'process_novel_batch', 'clean_text_ads', 'clean_text_breaks', 'character_material', 'current_plot', 'webnovel_writer'],

    isStatusOnlyPage(page) { const targetPage = this.logAliases[page] || page; return this.statusOnlyPages.includes(targetPage); },
    isLoglessPage(page) { const targetPage = this.logAliases[page] || page; return this.loglessPages.includes(targetPage); },
    isChapterExtractMode(mode) {
      return ['single', 'around', 'range'].includes(String(mode || ''));
    },
    taskLabel(mode) {
      return {
        single: '提取单章',
        around: '提取前后章',
        range: '提取范围',
        organizeSingle: '整理单章',
        organizeAround: '整理前后章',
        organizeRange: '整理范围',
        formatNovel: '格式化整本',
        formatFolder: '批量格式化',
      }[mode] || '任务';
    },
    setHeaderStatus(message, level = 'ready') {
      const badge = document.getElementById('statusBadge');
      if (!badge) return;
      const text = String(message || '就绪').trim() || '就绪';
      badge.className = `status-badge ${level === 'busy' ? 'busy' : level === 'error' ? 'error' : ''}`.trim();
      badge.innerHTML = `<i></i> ${this.escape(text)}`;
    },
    ...window.NovelUiMethods,
    ...window.NovelTaskPanelMethods,
    ...window.NovelCrawlerOutputMethods,
    ...window.NovelSplitterMethods,
    ...window.NovelCharacterMaterialMethods,
    ...window.NovelCurrentPlotMethods,
    ...window.NovelWebnovelWriterMethods,
    ...window.NovelFanqieAccountMethods,
    ...window.NovelFanqieTaskMethods,
    setConfigValue(path, value) {
      if (!path) return;
      const parts = String(path).split('.').filter(Boolean);
      let cursor = this.state.config;
      parts.slice(0, -1).forEach((part) => {
        if (!cursor[part] || typeof cursor[part] !== 'object') cursor[part] = {};
        cursor = cursor[part];
      });
      if (parts.length) cursor[parts[parts.length - 1]] = value;
    },
    debounceSavePage(page) {
      window.clearTimeout(this.saveTimer);
      this.saveTimer = window.setTimeout(() => this.persistPageConfig(page), 350);
    },
    async persistPageConfig(page) {
      try {
        if (page === 'process_novel') {
          this.state.config.process_novel = Object.assign({}, this.state.config.process_novel || {}, this.collectProcessConfig());
          this.state.config.clean_text = Object.assign({}, this.state.config.clean_text || {}, this.collectCleanTextConfig());
          this.state.config.novel_splitter = Object.assign({}, this.state.config.novel_splitter || {}, this.collectNovelSplitConfig());
        } else if (page === 'auto_publish') {
          this.state.config.auto_publish = this.collectPublishPayload('ap', this.state.config.auto_publish?.operation || 'publish');
        } else if (page === 'chapter_sync') {
          this.state.config.chapter_sync = this.collectPublishPayload('sy', this.state.config.chapter_sync?.operation || 'publish');
        } else if (page === 'web_crawler') {
          this.state.config.web_crawler = this.collectCrawlerConfig();
        } else if (page === 'character_material') {
          this.state.config.character_material = this.collectCharacterMaterialConfig();
        } else if (page === 'current_plot') {
          this.state.config.current_plot = this.collectCurrentPlotConfig();
        } else if (page === 'webnovel_writer') {
          this.state.config.webnovel_writer = this.collectWebnovelWriterConfig();
        }
        this.state.config.activePage = this.currentPage;
        await this.api.save_config(this.state.config);
      } catch (error) {
        console.debug('save config failed', error);
      }
    },
    bindFormAutosave(page) {
      const root = document.querySelector(`[data-page="${page}"] .fanqie-settings-card`);
      if (!root) return;
      const handler = () => this.debounceSavePage(page);
      root.addEventListener('input', handler);
      root.addEventListener('change', handler);
    },
    async init() {
      await this.waitForApi();
      this.state = await this.api.get_state();
      this.currentPage = pageTitles[this.state.config.activePage] ? this.state.config.activePage : defaultPage;
      this.bindShell();
      this.render();
    },
    waitForApi() {
      return new Promise((resolve) => {
        const ready = () => {
          this.api = window.pywebview && window.pywebview.api;
          if (this.api) resolve();
        };
        if (window.pywebview && window.pywebview.api) return ready();
        window.addEventListener('pywebviewready', ready, { once: true });
      });
    },
    bindShell() {
      const brandButton = document.getElementById('brandButton');
      const pageMenu = document.getElementById('pageMenu');
      const switchPage = (event) => {
        const button = event.target.closest('[data-page]');
        if (!button) return;
        pageMenu?.classList.remove('open');
        brandButton?.setAttribute('aria-expanded', 'false');
        this.hasUserSelectedPage = true;
        this.go(button.dataset.page);
      };
      brandButton?.addEventListener('click', (event) => {
        event.stopPropagation();
        const isOpen = pageMenu?.classList.toggle('open');
        brandButton.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      });
      pageMenu?.addEventListener('click', switchPage);
      document.addEventListener('click', () => {
        pageMenu?.classList.remove('open');
        brandButton?.setAttribute('aria-expanded', 'false');
      });
      document.getElementById('loginButton')?.addEventListener('click', async () => {
        if (!this.api.reset_login) return;
        this.setHeaderStatus('正在重置授权...', 'busy');
        try {
          const result = await this.api.reset_login();
          this.setHeaderStatus(result && result.ok ? '授权已清除' : '授权清理失败', result && result.ok ? 'ready' : 'error');
        } catch (error) {
          console.debug('reset login failed', error);
          this.setHeaderStatus('授权清理失败', 'error');
        }
      });
      document.getElementById('resetDataButton')?.addEventListener('click', async () => {
        if (!this.api.reset_app_data) return;
        this.setHeaderStatus('正在重置数据...', 'busy');
        try {
          const result = await this.api.reset_app_data();
          this.state = await this.api.get_state();
          this.currentPage = pageTitles[this.state.config.activePage] ? this.state.config.activePage : defaultPage;
          this.logs = {
            process_novel: [],
            process_novel_batch: [],
            clean_text_ads: [],
            clean_text_breaks: [],
            novel_splitter: [],
            auto_publish: [],
            chapter_sync: [],
            web_crawler: [],
            character_material: [],
            current_plot: [],
            webnovel_writer: [],
          };
          this.lastOutputs = {};
          this.lastBackups = {};
          this.taskStatus = {};
          this.progressState = {};
          this.taskStore = window.NovelTaskStateStore ? window.NovelTaskStateStore.create() : null;
          this.activeResultModes = {};
          this.resultTexts = {};
          this.render();
          this.setHeaderStatus(result && result.ok ? '数据已重建' : '重建失败', result && result.ok ? 'ready' : 'error');
        } catch (error) {
          console.debug('reset data failed', error);
          this.setHeaderStatus('重建失败', 'error');
        }
      });
      this.bindThemeControls();
      document.body.addEventListener('click', async (event) => {
        const copy = event.target.closest('[data-copy-output]');
        if (copy) this.copyOutput(copy.dataset.copyOutput);
        const clear = event.target.closest('[data-clear-output]');
        if (clear) this.clearOutput(clear.dataset.clearOutput);
        const openOutput = event.target.closest('[data-open-output]');
        if (openOutput) await this.openOutputDir(openOutput.dataset.openOutput);
        const openLog = event.target.closest('[data-open-log]');
        if (openLog) await this.openTaskLog(openLog.dataset.openLog);
        const openBackup = event.target.closest('[data-open-backup]');
        if (openBackup) await this.openBackup(openBackup.dataset.openBackup);
      });
    },
    bindThemeControls() {
      const modal = document.getElementById('themeModal');
      document.getElementById('themeButton')?.addEventListener('click', () => modal?.classList.add('open'));
      document.getElementById('themeClose')?.addEventListener('click', () => modal?.classList.remove('open'));
      modal?.addEventListener('click', (event) => {
        if (event.target === modal) modal.classList.remove('open');
      });
      document.querySelectorAll('[data-theme]').forEach((button) => button.addEventListener('click', () => {
        const theme = button.dataset.theme || 'blue';
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
      }));
      document.documentElement.setAttribute('data-theme', localStorage.getItem('theme') || 'blue');
    },
    async saveConfig() {
      this.state.config.activePage = this.currentPage;
      await this.api.save_config(this.state.config);
    },
    async go(page) {
      this.currentPage = pageTitles[page] ? page : defaultPage;
      this.render();
      await this.saveConfig();
    },
    render() {
      const [, title] = pageTitles[this.currentPage] || pageTitles[defaultPage];
      document.title = this.hasUserSelectedPage ? `${title} - 番茄发布同步助手` : '番茄发布同步助手';
      const brandModeText = document.getElementById('brandModeText');
      if (brandModeText) brandModeText.textContent = this.hasUserSelectedPage ? title : 'LOCAL TOOL';
      document.querySelectorAll('#pageMenu [data-page]').forEach((button) => button.classList.toggle('active', button.dataset.page === this.currentPage));
      const renderer = {
        process_novel: window.renderNovelProcessorPage,
        auto_publish: window.renderFanqiePublisherPage,
        chapter_sync: window.renderFanqieSyncerPage,
        web_crawler: window.renderNovelCrawlerPage,
        character_material: window.renderCharacterMaterialPage,
        current_plot: window.renderCurrentPlotPage,
        webnovel_writer: window.renderWebnovelWriterPage,
      }[this.currentPage] || window.renderNovelProcessorPage;
      document.getElementById('pageHost').innerHTML = renderer(this);
      this.bindPage(this.currentPage);
      this.restorePageLogs();
    },
    restorePageLogs() {
      if (this.currentPage === 'process_novel') {
        ['process_novel', 'novel_splitter', 'process_novel_batch', 'clean_text_ads', 'clean_text_breaks'].forEach((page) => this.restoreLog(page));
      } else {
        this.restoreLog(this.currentPage);
      }
    },
    bindPage(page) {
      if (page === 'process_novel') this.bindProcessNovelPage();
      if (page === 'auto_publish') this.bindAutoPublishPage();
      if (page === 'chapter_sync') this.bindChapterSyncPage();
      if (page === 'web_crawler') this.bindWebCrawlerPage();
      if (page === 'character_material') this.bindCharacterMaterialPage();
      if (page === 'current_plot') this.bindCurrentPlotPage();
      if (page === 'webnovel_writer') this.bindWebnovelWriterPage();
      this.bindFormAutosave(page);
    },

    bindProcessNovelPage() {
      this.bindChooseFile('exChooseNovel', 'process_novel.novelFile', 'exNovelFile', '选择完整小说 TXT', async (path) => {
        this.updateFilePicker('tcAdInput', path, '选择 TXT');
        this.updateFilePicker('tcMoveInput', path, '选择 TXT');
        await this.api.process_novel_analyze(path);
      });
      this.bindChooseFolder('exChooseBatchFolder', 'process_novel.batchFolder', 'exBatchFolder', '选择文件夹', (path) => {
        this.updateFilePicker('tcAdFolder', path, '选择文件夹');
        this.updateFilePicker('tcMoveFolder', path, '选择文件夹');
      });
      this.bindChooseFile('exChooseOutputFile', 'process_novel.outputFile', 'exOutputFile', '自动命名 / 选择输出 TXT', null, true);
      document.querySelectorAll('[data-ex-mode]').forEach((button) => button.addEventListener('click', () => this.runProcessNovel(button.dataset.exMode, button.dataset.exLog || 'process_novel')));
      this.bindChooseFile('tcChooseAdInput', 'clean_text.adInputFile', 'tcAdInput', '选择 TXT');
      this.bindChooseFolder('tcChooseAdFolder', 'clean_text.adBatchFolder', 'tcAdFolder', '选择文件夹');
      this.bindChooseFile('tcChooseMoveInput', 'clean_text.moveInputFile', 'tcMoveInput', '选择 TXT');
      this.bindChooseFolder('tcChooseMoveFolder', 'clean_text.moveBatchFolder', 'tcMoveFolder', '选择文件夹');
      document.getElementById('tcAdRun')?.addEventListener('click', () => this.runCleanText('ad'));
      document.getElementById('tcMoveRun')?.addEventListener('click', () => this.runCleanText('move'));
      this.bindNovelSplitterControls();
    },
    collectProcessConfig() {
      return {
        novelFile: document.getElementById('exNovelFile')?.value || '',
        batchFolder: document.getElementById('exBatchFolder')?.value || '',
        outputFile: document.getElementById('exOutputFile')?.value || '',
        chapter: Number(document.getElementById('exChapter')?.value || 0),
        aroundChapter: Number(document.getElementById('exAroundChapter')?.value || 0),
        start: Number(document.getElementById('exStart')?.value || 0),
        end: Number(document.getElementById('exEnd')?.value || 0),
      };
    },
    collectCleanTextConfig() {
      return {
        adInputFile: document.getElementById('tcAdInput')?.value || '',
        adBatchFolder: document.getElementById('tcAdFolder')?.value || '',
        moveInputFile: document.getElementById('tcMoveInput')?.value || '',
        moveBatchFolder: document.getElementById('tcMoveFolder')?.value || '',
        adProfile: document.getElementById('tcAdProfile')?.value || 'default',
        overwrite: !!document.getElementById('tcAdOverwrite')?.checked,
        backup: !!document.getElementById('tcAdBackup')?.checked,
        normalizePunctuation: document.getElementById('tcMovePunctuation')?.value !== 'off',
        maxMoveChars: Number(document.getElementById('tcMaxMoveChars')?.value || 120),
      };
    },
    async runProcessNovel(mode, logTarget) {
      const payload = Object.assign({}, this.collectProcessConfig(), { mode, logTarget });
      const targetPage = this.logAliases[logTarget] || logTarget || 'process_novel';
      this.activeResultModes[targetPage] = this.isChapterExtractMode(mode) ? 'chapter_text' : '';
      this.resultTexts[targetPage] = '';
      this.state.config.process_novel = payload;
      await this.saveConfig();
      this.beginTaskUi(logTarget, `${this.taskLabel(mode)}中...`);
      const ok = await this.api.process_novel_run(payload);
      if (!ok) this.toast('任务没有启动，请查看日志。', 'warning', logTarget);
    },
    async runCleanText(scope) {
      const isMove = scope === 'move';
      const logTarget = isMove ? 'clean_text_breaks' : 'clean_text_ads';
      const saved = this.collectCleanTextConfig();
      const payload = Object.assign({}, saved, {
        scope,
        inputFile: document.getElementById(isMove ? 'tcMoveInput' : 'tcAdInput')?.value || '',
        batchFolder: document.getElementById(isMove ? 'tcMoveFolder' : 'tcAdFolder')?.value || '',
        overwrite: !!document.getElementById(isMove ? 'tcMoveOverwrite' : 'tcAdOverwrite')?.checked,
        backup: !!document.getElementById(isMove ? 'tcMoveBackup' : 'tcAdBackup')?.checked,
      });
      this.state.config.clean_text = Object.assign({}, this.state.config.clean_text || {}, saved, payload);
      await this.saveConfig();
      this.beginTaskUi(logTarget, isMove ? '修复句子中...' : '清理广告中...');
      const ok = await this.api.clean_text_run(payload);
      if (!ok) this.toast('任务没有启动，请查看日志。', 'warning', logTarget);
    },

    async stopTask(apiName, page) {
      if (!this.api[apiName]) return this.toast('当前版本不支持停止任务。', 'warning', page);
      const ok = await this.api[apiName]();
      if (!ok) this.toast('当前没有正在运行的任务。', 'warning', page);
    },

    bindWebCrawlerPage() {
      this.bindCrawlerOutputControls();
      document.getElementById('nsRun')?.addEventListener('click', () => this.runWebCrawler());
      document.getElementById('nsStop')?.addEventListener('click', () => this.stopTask('web_crawler_stop', 'web_crawler'));
    },
    collectCrawlerConfig() {
      return {
        novelUrl: document.getElementById('nsUrl')?.value || '',
        outputFile: document.getElementById('nsOutput')?.value || '',
        outputFileManual: !!(this.state.config.web_crawler || {}).outputFileManual,
        outputAutoUrl: (this.state.config.web_crawler || {}).outputAutoUrl || '',
        start: Number(document.getElementById('nsStart')?.value || 1),
        end: Number(document.getElementById('nsEnd')?.value || 0),
        maxWorkers: Number(document.getElementById('nsWorkers')?.value || 16),
        timeout: Number(document.getElementById('nsTimeout')?.value || 25),
        requestDelayMin: Number(document.getElementById('nsDelayMin')?.value || 0.12),
        requestDelayMax: Number(document.getElementById('nsDelayMax')?.value || 0.35),
        maxRetries: Number(document.getElementById('nsRetries')?.value || 3),
        htmlFallback: !!document.getElementById('nsHtmlFallback')?.checked,
        detailedLog: !!document.getElementById('nsDetailedLog')?.checked,
      };
    },
    async runWebCrawler() {
      const cfg = this.state.config.web_crawler || {};
      if (!cfg.outputFileManual && !(document.getElementById('nsOutput')?.value || '').trim()) {
        await this.refreshCrawlerAutoOutput(true);
      }
      const payload = this.collectCrawlerConfig();
      this.state.config.web_crawler = payload;
      await this.saveConfig();
      this.beginTaskUi('web_crawler', '准备启动网页抓取...');
      const ok = await this.api.web_crawler_run(payload);
      if (!ok) this.toast('任务没有启动，请查看日志。', 'warning', 'web_crawler');
    },

    bindChooseFile(buttonId, configPath, inputId, emptyText, afterChoose, save = false, suggestedName = '') {
      document.getElementById(buttonId)?.addEventListener('click', async () => {
        const filename = typeof suggestedName === 'function' ? suggestedName() : suggestedName;
        const path = await this.api.choose_file(configPath, save, filename || 'output.txt');
        if (!path) return;
        this.setConfigValue(configPath, path);
        this.updateFilePicker(inputId, path, emptyText);
        if (afterChoose) await afterChoose(path);
        await this.persistPageConfig(this.currentPage);
      });
    },
    bindChooseFolder(buttonId, configPath, inputId, emptyText, afterChoose) {
      document.getElementById(buttonId)?.addEventListener('click', async () => {
        const path = await this.api.choose_folder(configPath);
        if (!path) return;
        this.setConfigValue(configPath, path);
        this.updateFilePicker(inputId, path, emptyText);
        if (afterChoose) await afterChoose(path);
        await this.persistPageConfig(this.currentPage);
      });
    },

  };

  window.NovelTools = app;
  app.init().catch((error) => {
    console.error(error);
    document.getElementById('pageHost').innerHTML = `<div class="card"><h2>启动失败</h2><p>${String(error)}</p></div>`;
  });
})();
