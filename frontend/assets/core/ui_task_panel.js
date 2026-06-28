(function () {
  window.NovelTaskPanelMethods = {
    renderTerminalPanel(page) {
      const statusOnly = this.isStatusOnlyPage(page);
      const logless = this.isLoglessPage(page);
      const isWebnovel = (this.logAliases[page] || page) === 'webnovel_writer';
      const actions = isWebnovel
        ? `<button class="terminal-open-log" data-open-log="${this.attr(page)}" type="button">打开日志</button>
            <button class="terminal-open" data-open-output="${this.attr(page)}" type="button">打开目录</button>`
        : `<button class="terminal-clear" data-clear-output="${this.attr(page)}" type="button">清空</button>
            <button class="terminal-copy" data-copy-output="${this.attr(page)}" type="button">复制</button>
            <button class="terminal-open-log" data-open-log="${this.attr(page)}" type="button">打开日志</button>
            <button class="terminal-open-backup" data-open-backup="${this.attr(page)}" type="button">打开备份</button>
            <button class="terminal-open" data-open-output="${this.attr(page)}" type="button">打开目录</button>`;
      return `<div class="terminal-card ${statusOnly ? 'status-panel' : ''} ${logless ? 'logless-panel' : ''}">
        <div class="terminal-head">
          <div class="terminal-dots"><i></i><i></i><i></i></div>
          <b>任务进度</b>
          <div class="terminal-actions">
            ${actions}
          </div>
        </div>
        <div class="terminal-progress" id="${this.attr(page)}ProgressWrap">
          <span id="${this.attr(page)}ProgressText">0/0</span>
          <div class="progress" id="${this.attr(page)}ProgressTrack"><i id="${this.attr(page)}ProgressBar"></i></div>
          <span id="${this.attr(page)}ProgressPercent">0%</span>
        </div>
        <div class="terminal-status info" id="${this.attr(page)}Status">等待执行</div>
        ${logless ? '' : `<div class="terminal-log" id="${this.attr(page)}Log"></div>`}
      </div>`;
    },

    statePath(key) {
      return (this.state && this.state.paths && this.state.paths[key]) || key;
    },
    outputPathForPage(page) {
      const featureRootPages = {
        process_novel: 'novel_processor',
        process_novel_batch: 'novel_processor',
        novel_splitter: 'novel_processor',
        clean_text_ads: 'novel_processor',
        clean_text_breaks: 'novel_processor',
        auto_publish: 'fanqie_publisher',
        chapter_sync: 'fanqie_syncer',
        character_material: 'character_material',
        current_plot: 'current_plot',
        webnovel_writer: 'webnovel_writer',
      };
      if (featureRootPages[page]) return this.statePath(featureRootPages[page]);
      if (page === 'web_crawler') return document.getElementById('nsOutput')?.value || this.lastOutputs.web_crawler || this.statePath('web_crawler_outputs');
      return this.lastOutputs[page] || this.statePath('data');
    },
    async openOutputDir(page) {
      const path = this.outputPathForPage(page);
      if (!path || !this.api.open_path) return this.toast('没有可打开的输出目录。', 'warning', page);
      const ok = await this.api.open_path(path);
      if (!ok) this.toast('打开输出目录失败。', 'error', page);
    },
    async openTaskLog(page) {
      if (!this.api.open_log) return this.toast('当前版本不支持直接打开日志。', 'warning', page);
      const ok = await this.api.open_log(page);
      if (!ok) this.toast('打开日志失败。', 'error', page);
    },
    async openBackup(page) {
      const path = this.lastBackups[page] || '';
      if (!path || !this.api.open_backup) return this.toast('当前任务暂无可打开的备份。', 'warning', page);
      const ok = await this.api.open_backup(path);
      if (!ok) this.toast('打开备份失败。', 'error', page);
    },

    beginTaskUi(page, message) {
      const targetPage = this.logAliases[page] || page;
      this.logs[targetPage] = [];
      if (this.resultTexts) this.resultTexts[targetPage] = '';
      this.progressState[targetPage] = { current: 0, total: 1 };
      if (this.taskStore) this.taskStore.begin(targetPage, message || '任务启动中...');
      this.setProgress(targetPage, 0, 1);
      this.setTaskStatus(targetPage, message || '任务启动中...', 'info');
      this.setTaskSummary(targetPage, '暂无', 'info');
      const box = document.getElementById(`${targetPage}Log`);
      if (box) {
        box.innerHTML = '';
        box.classList.toggle('result-text', this.activeResultModes?.[targetPage] === 'chapter_text');
      }
    },
    setTaskStatus(page, message, level = 'info') {
      const targetPage = this.logAliases[page] || page;
      const text = String(message || '').trim();
      if (!text) return;
      this.taskStatus[targetPage] = { message: text, level };
      this.renderTaskMetrics(targetPage);
      const node = document.getElementById(`${targetPage}Status`);
      if (node) {
        const cssLevel = level === 'warning' ? 'warn' : level;
        node.className = `terminal-status ${cssLevel}`;
        node.textContent = text;
      }
      if (targetPage === this.currentPage) {
        const headerLevel = level === 'error' ? 'error' : (level === 'success' ? 'ready' : 'busy');
        const headerText = level === 'error' ? '任务失败' : (level === 'success' ? '任务完成' : '任务运行中');
        this.setHeaderStatus(headerText, headerLevel);
      }
    },
    setTaskSummary(page, summary, level = 'info') {
      // 右侧面板不再显示“最近结果”；任务详情写入日志文件，动态栏显示当前状态。
    },
    conciseTaskMessage(message, page = '') {
      const text = String(message || '').trim();
      if (!text) return '';
      if (text.startsWith('详细日志：')) return '';
      if (text.startsWith('开始：')) return '';
      if (text.startsWith('准备执行：')) {
        return text.replace(/^准备执行：/, '');
      }
      if (page === 'web_crawler') {
        if (/^(抓取|写入|限流|失败)：第\s*\d+\s*章/.test(text)) return text;
        if (/^(目录：读取|读取目录：)/.test(text)) return '正在读取目录...';
        if (/^(目录：完成|目录完成：)/.test(text)) {
          const match = text.match(/本次\s*(\d+)\s*章/);
          return match ? `目录读取完成：本次 ${match[1]} 章。` : '目录读取完成。';
        }
        if (/^(阶段：第一组参数抓取：|开始第一组参数抓取)/.test(text)) return '正在抓取章节...';
        if (/^(阶段：第一组参数抓取完成|第一组参数抓取完成)/.test(text)) return text.includes('失败') ? '第一轮完成，正在补抓失败章节...' : '章节抓取完成，正在写出文件...';
        if (/^(补抓：上一组|上一组完成后仍失败)/.test(text)) return '正在补抓失败章节...';
        if (/^(限流：|触发限流保护)/.test(text)) return '触发限流保护，稍后继续...';
        if (/^正在合并/.test(text)) return '正在合并并写出 TXT 文件...';
        if (/^(完成：TXT|TXT 文件写出完成)/.test(text)) return 'TXT 文件已写出。';
      }
      return text;
    },

    async copyOutput(page) {
      const resultText = String(this.resultTexts?.[page] || '').trim();
      const logText = (document.getElementById(`${page}Log`)?.innerText || '').trim();
      const statusText = (document.getElementById(`${page}Status`)?.innerText || '').trim();
      const text = resultText || logText || statusText;
      if (!text) return this.toast('暂无可复制内容。', 'warning', page);
      try {
        await navigator.clipboard.writeText(text);
        this.toast('已复制。', 'success', page);
      } catch (_) {
        const area = document.createElement('textarea');
        area.value = text;
        area.style.position = 'fixed';
        area.style.left = '-9999px';
        document.body.appendChild(area);
        area.select();
        document.execCommand('copy');
        area.remove();
        this.toast('已复制。', 'success', page);
      }
    },
    applyTaskEvent(event) {
      const page = event && event.page ? event.page : this.currentPage;
      const targetPage = this.logAliases[page] || page;
      const state = this.taskStore ? this.taskStore.applyEvent(event || {}) : null;
      const progress = event && event.payload && event.payload.progress;
      if (progress) this.setProgress(targetPage, progress.current, progress.total);
      this.renderTaskMetrics(targetPage, state);
      if (event && event.eventType === 'progress') return;
      const text = event && event.displayMessage ? event.displayMessage : (event && event.label && event.message ? `${event.label}：${event.message}` : event && event.message);
      this.appendLog(targetPage, text, event && event.level || 'info');
    },
    renderTaskMetrics(page, state = null) {
      const targetPage = this.logAliases[page] || page;
      if (state && this.taskStore) this.taskStore.states[targetPage] = state;
    },
    appendLog(page, message, level = 'info') {
      const targetPage = this.logAliases[page] || page;
      const normalizedLevel = level === 'warning' ? 'warn' : level;
      const text = this.conciseTaskMessage(message, targetPage);
      if (!text) return;
      this.setTaskStatus(targetPage, text, normalizedLevel);
      if (this.isLoglessPage(targetPage)) return;
      const isCrawlerChapterLine = /^(抓取|写入|限流|失败)：第\s*\d+\s*章/.test(text);
      if (targetPage === 'web_crawler' && !isCrawlerChapterLine) return;
      if (!this.logs[targetPage]) this.logs[targetPage] = [];
      const item = { message: text, level: normalizedLevel, time: new Date().toLocaleTimeString() };
      const last = this.logs[targetPage].slice(-1)[0];
      if (last && last.message === item.message && last.level === item.level) return;
      this.logs[targetPage].push(item);
      const box = document.getElementById(`${targetPage}Log`);
      if (!box) return;
      const line = document.createElement('div');
      line.className = `log-line ${normalizedLevel}`;
      line.textContent = text;
      box.appendChild(line);
      box.scrollTop = box.scrollHeight;
    },
    restoreLog(page) {
      const box = document.getElementById(`${page}Log`);
      const status = this.taskStatus[page];
      const statusNode = document.getElementById(`${page}Status`);
      if (statusNode) {
        statusNode.textContent = status?.message || '等待执行';
        const cssLevel = status?.level === 'warning' ? 'warn' : (status?.level || 'info');
        statusNode.className = `terminal-status ${cssLevel}`;
      }
      const progress = this.progressState[page];
      if (progress) this.setProgress(page, progress.current, progress.total);
      this.renderTaskMetrics(page);
      if (!box) return;
      box.innerHTML = '';
      box.classList.remove('result-text');
      if (this.resultTexts?.[page]) {
        this.showResultText(page, this.resultTexts[page]);
        return;
      }
      (this.logs[page] || []).forEach((item) => {
        const line = document.createElement('div');
        line.className = `log-line ${item.level}`;
        line.textContent = item.message;
        box.appendChild(line);
      });
      if (!box.innerHTML && this.activeResultModes?.[page] === 'chapter_text') box.innerHTML = '';
      box.scrollTop = box.scrollHeight;
    },
    clearOutput(page) {
      this.logs[page] = [];
      if (this.resultTexts) this.resultTexts[page] = '';
      if (this.activeResultModes) this.activeResultModes[page] = '';
      this.progressState[page] = { current: 0, total: 0 };
      if (this.taskStore) this.taskStore.begin(page, '等待执行');
      this.setProgress(page, 0, 0);
      this.setTaskStatus(page, '等待执行', 'info');
      this.setTaskSummary(page, '暂无', 'info');
      const box = document.getElementById(`${page}Log`);
      if (box) {
        box.classList.remove('result-text');
        box.innerHTML = '';
      }
    },
    showResultText(page, text) {
      const targetPage = this.logAliases[page] || page;
      const box = document.getElementById(`${targetPage}Log`);
      if (!box) return;
      box.innerHTML = '';
      box.classList.add('result-text');
      box.textContent = String(text || '');
      box.scrollTop = 0;
    },
    setProgress(page, current, total) {
      const targetPage = this.logAliases[page] || page;
      const totalValue = Math.max(0, Number(total || 0));
      const rawCurrent = Math.max(0, Number(current || 0));
      const currentValue = totalValue > 0 ? Math.min(rawCurrent, totalValue) : rawCurrent;
      const percent = totalValue > 0 ? Math.max(0, Math.min(100, Math.round((currentValue / totalValue) * 100))) : 0;
      this.progressState[targetPage] = { current: currentValue, total: totalValue };
      if (this.taskStore) this.taskStore.setProgress(targetPage, currentValue, totalValue);
      const displayTotal = totalValue > 0 ? Math.ceil(totalValue) : 0;
      const displayCurrent = totalValue > 0 ? (currentValue <= 0 ? 0 : Math.min(displayTotal, Math.ceil(currentValue))) : 0;
      const text = document.getElementById(`${targetPage}ProgressText`);
      const bar = document.getElementById(`${targetPage}ProgressBar`);
      const track = document.getElementById(`${targetPage}ProgressTrack`);
      const percentText = document.getElementById(`${targetPage}ProgressPercent`);
      if (text) text.textContent = `${displayCurrent}/${displayTotal}`;
      if (bar) bar.style.width = `${percent}%`;
      if (percentText) percentText.textContent = `${percent}%`;
      if (track) track.classList.toggle('running', percent > 0 && percent < 100);
      this.renderTaskMetrics(targetPage);
    },
    taskDone(page, ok, result) {
      const targetPage = this.logAliases[page] || page;
      const message = result && result.message ? result.message : (ok ? '任务完成' : '任务失败');
      const state = this.progressState[targetPage] || { current: 0, total: 1 };
      if (ok) this.setProgress(targetPage, state.total || 1, state.total || 1);
      if (result && result.path) this.lastOutputs[targetPage] = result.path;
      if (result && result.backupPath) this.lastBackups[targetPage] = result.backupPath;
      else if (result && result.backupDir) this.lastBackups[targetPage] = result.backupDir;
      else if (result && Array.isArray(result.backupPaths) && result.backupPaths.length) this.lastBackups[targetPage] = result.backupPaths[result.backupPaths.length - 1];

      const finalMessage = ok ? message : `${message}（详情见对应 tasklogs 目录）`;
      if (this.taskStore) this.taskStore.finish(targetPage, ok, finalMessage);
      this.setTaskStatus(targetPage, finalMessage, ok ? 'success' : 'error');
      this.resultTexts[targetPage] = finalMessage;
      this.setTaskSummary(targetPage, finalMessage, ok ? 'success' : 'error');

      const resultDisplayMode = result && result.resultDisplayMode ? String(result.resultDisplayMode) : '';
      const resultText = result && result.resultText ? String(result.resultText) : '';
      if (targetPage !== 'webnovel_writer' && ok && resultDisplayMode === 'chapter_text') {
        this.activeResultModes[targetPage] = 'chapter_text';
        this.resultTexts[targetPage] = resultText;
        this.showResultText(targetPage, resultText);
        return;
      }

      if (targetPage !== 'webnovel_writer') this.resultTexts[targetPage] = '';
      const box = document.getElementById(`${targetPage}Log`);
      if (box) {
        box.classList.remove('result-text');
        box.innerHTML = '';
      }
    },
    toast(message, level = 'info', page = this.currentPage) {
      const text = String(message || '').trim();
      if (!text) return;
      if (this.isLoglessPage(page) && text === '已复制。') return;
      this.appendLog(page, text, level);
    }
  };
})();

(function () {
  window.NovelFanqieAccountMethods = {
    renderFanqieLoginStateRow(prefix, cfg = {}) {
      return `<div class="field fanqie-login-state-row">
        <label>登录状态</label>
        ${this.filePicker(`${prefix}AuthStatePath`, cfg.authStatePath || '', `${prefix}ChooseAuthState`, '默认 state.json')}
      </div>`;
    },
    bindFanqieLoginStateControls(prefix, configPath) {
      document.getElementById(`${prefix}ChooseAuthState`)?.addEventListener('click', async () => {
        const path = this.api.choose_login_state
          ? await this.api.choose_login_state(configPath)
          : await this.api.choose_file(configPath, false, 'state.json');
        if (!path) return;
        this.setConfigValue(configPath, path);
        this.updateFilePicker(`${prefix}AuthStatePath`, path, '默认 state.json');
        await this.persistPageConfig(this.currentPage);
      });
    },
  };
})();
(function () {
  window.NovelFanqieTaskMethods = {
    bindAutoPublishPage() {
      this.bindChooseSource('apChooseNovel', 'auto_publish.novelFile', 'apNovelFile', '选择小说来源');
      document.querySelectorAll('[data-auto-op]').forEach((button) => button.addEventListener('click', () => this.runAutoPublish(button.dataset.autoOp)));
      document.getElementById('apStop')?.addEventListener('click', () => this.stopTask('auto_publish_stop', 'auto_publish'));
      document.getElementById('apPause')?.addEventListener('click', () => this.stopTask('auto_publish_pause', 'auto_publish'));
      document.getElementById('apResume')?.addEventListener('click', () => this.stopTask('auto_publish_resume', 'auto_publish'));
      this.bindFanqieLoginStateControls('ap', 'auto_publish.authStatePath');
      this.bindManualScheduleToggle('ap');
    },
    async runAutoPublish(operation) {
      const payload = this.collectPublishPayload('ap', operation);
      this.state.config.auto_publish = payload;
      await this.saveConfig();
      this.beginTaskUi('auto_publish', '准备启动番茄发布...');
      const ok = await this.api.auto_publish_run(payload);
      if (!ok) this.toast('任务没有启动，请查看日志。', 'warning', 'auto_publish');
    },

    bindChapterSyncPage() {
      this.bindChooseSource('syChooseNovel', 'chapter_sync.novelFile', 'syNovelFile', '选择小说来源');
      document.querySelectorAll('[data-sync-op]').forEach((button) => button.addEventListener('click', () => this.runChapterSync(button.dataset.syncOp)));
      document.getElementById('syStop')?.addEventListener('click', () => this.stopTask('chapter_sync_stop', 'chapter_sync'));
      document.getElementById('syPause')?.addEventListener('click', () => this.stopTask('chapter_sync_pause', 'chapter_sync'));
      document.getElementById('syResume')?.addEventListener('click', () => this.stopTask('chapter_sync_resume', 'chapter_sync'));
      this.bindFanqieLoginStateControls('sy', 'chapter_sync.authStatePath');
    },
    async runChapterSync(operation) {
      const payload = this.collectPublishPayload('sy', operation);
      this.state.config.chapter_sync = payload;
      await this.saveConfig();
      this.beginTaskUi('chapter_sync', '准备启动番茄同步...');
      const ok = await this.api.chapter_sync_run(payload);
      if (!ok) this.toast('任务没有启动，请查看日志。', 'warning', 'chapter_sync');
    },
    bindManualScheduleToggle(prefix) {
      const checkbox = document.getElementById(`${prefix}ManualSchedule`);
      const fields = document.getElementById(`${prefix}ManualScheduleFields`);
      const sync = () => fields?.classList.toggle('hidden', !checkbox?.checked);
      checkbox?.addEventListener('change', sync);
      sync();
    },
    bindChooseSource(buttonId, configPath, inputId, emptyText, afterChoose) {
      document.getElementById(buttonId)?.addEventListener('click', async () => {
        const path = this.api.choose_source
          ? await this.api.choose_source(configPath)
          : await this.api.choose_file(configPath, false, 'novel.txt');
        if (!path) return;
        this.setConfigValue(configPath, path);
        this.updateFilePicker(inputId, path, emptyText);
        if (afterChoose) await afterChoose(path);
        await this.persistPageConfig(this.currentPage);
      });
    },
    collectPublishPayload(prefix, operation) {
      return {
        novelFile: document.getElementById(`${prefix}NovelFile`)?.value || '',
        chapterManageUrl: document.getElementById(`${prefix}Url`)?.value || '',
        authStatePath: document.getElementById(`${prefix}AuthStatePath`)?.value || '',
        start: Number(document.getElementById(`${prefix}Start`)?.value || 1),
        end: Number(document.getElementById(`${prefix}End`)?.value || 1),
        useAi: !!document.getElementById(`${prefix}UseAi`)?.checked,
        verifyAfterPublish: !!document.getElementById(`${prefix}VerifyAfterPublish`)?.checked,
        debugScreenshots: !!document.getElementById(`${prefix}DebugScreenshots`)?.checked,
        failureScreenshots: !!document.getElementById(`${prefix}FailureScreenshots`)?.checked,
        gitTracking: !!document.getElementById(`${prefix}GitTracking`)?.checked,
        cleanBeforeRun: !!document.getElementById(`${prefix}CleanBeforeRun`)?.checked,
        headless: !!document.getElementById(`${prefix}Headless`)?.checked,
        manualSchedule: !!document.getElementById(`${prefix}ManualSchedule`)?.checked,
        scheduleStartDate: document.getElementById(`${prefix}ScheduleStartDate`)?.value || '',
        scheduleMorningTime: document.getElementById(`${prefix}ScheduleMorningTime`)?.value || '10:00',
        scheduleMorningCount: Number(document.getElementById(`${prefix}ScheduleMorningCount`)?.value || 1),
        scheduleAfternoonTime: document.getElementById(`${prefix}ScheduleAfternoonTime`)?.value || '18:00',
        scheduleAfternoonCount: Number(document.getElementById(`${prefix}ScheduleAfternoonCount`)?.value || 0),
        operation,
      };
    },
  };
})();
