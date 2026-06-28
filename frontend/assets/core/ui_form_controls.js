(function () {
  window.NovelUiMethods = {
    escape(value) {
      return String(value ?? '').replace(/[&<>'"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[ch]));
    },
    attr(value) {
      return this.escape(value);
    },
    basename(path) {
      const text = String(path || '').trim();
      if (!text) return '';
      const items = text.split(/\r?\n/).map(item => item.trim()).filter(Boolean);
      if (items.length > 1) return `${items.length} 个文件`;
      const cleaned = items[0].replace(/[\\/]+$/, '');
      const parts = cleaned.split(/[\\/]+/);
      return parts[parts.length - 1] || cleaned;
    },
    filePicker(inputId, value, buttonId, emptyText) {
      const name = this.basename(value);
      return `<input type="hidden" id="${this.attr(inputId)}" value="${this.attr(value || '')}" />
        <div class="file-picker ${name ? '' : 'empty'}" data-file-picker="${this.attr(inputId)}">
          <div class="file-meta"><span>已选择</span><strong id="${this.attr(inputId)}Name">${this.escape(name || emptyText || '未选择')}</strong></div>
          <button class="ghost-btn" id="${this.attr(buttonId)}" type="button">选择</button>
        </div>`;
    },
    updateFilePicker(inputId, path, emptyText) {
      const input = document.getElementById(inputId);
      if (input) input.value = path || '';
      const label = document.getElementById(`${inputId}Name`);
      if (label) label.textContent = this.basename(path) || emptyText || '未选择';
      const picker = document.querySelector(`[data-file-picker="${inputId}"]`);
      if (picker) picker.classList.toggle('empty', !this.basename(path));
    }
  };
})();
(function () {
  window.NovelCrawlerOutputMethods = {
    bindCrawlerOutputControls() {
      const cfg = this.state.config.web_crawler || (this.state.config.web_crawler = {});
      const urlInput = document.getElementById('nsUrl');
      const getSuggestedName = () => this.basename(document.getElementById('nsOutput')?.value || '') || 'output.txt';

      this.bindChooseFile(
        'nsChooseOutput',
        'web_crawler.outputFile',
        'nsOutput',
        '自动生成 / 选择文件',
        async (path) => {
          cfg.outputFileManual = true;
          cfg.outputAutoUrl = urlInput?.value || '';
          cfg.outputFile = path;
        },
        true,
        getSuggestedName,
      );

      let timer = null;
      urlInput?.addEventListener('input', () => {
        const nextUrl = (urlInput.value || '').trim();
        if (!cfg.outputFileManual) {
          this.updateFilePicker('nsOutput', '', nextUrl ? '正在解析书名...' : '自动生成 / 选择文件');
        }
        window.clearTimeout(timer);
        timer = window.setTimeout(() => this.refreshCrawlerAutoOutput(false), 650);
      });

      if ((urlInput?.value || '').trim() && !cfg.outputFileManual && !cfg.outputFile) {
        this.refreshCrawlerAutoOutput(false);
      }
    },
    async refreshCrawlerAutoOutput(force = false) {
      const cfg = this.state.config.web_crawler || (this.state.config.web_crawler = {});
      if (cfg.outputFileManual && !force) return;
      const url = (document.getElementById('nsUrl')?.value || '').trim();
      if (!url || !this.api.web_crawler_preview) {
        if (!url) {
          cfg.outputFile = '';
          cfg.outputAutoUrl = '';
          cfg.outputFileManual = false;
          this.updateFilePicker('nsOutput', '', '自动生成 / 选择文件');
        }
        return;
      }
      const token = `${Date.now()}-${Math.random()}`;
      this._crawlerPreviewToken = token;
      try {
        const result = await this.api.web_crawler_preview(url, '');
        if (this._crawlerPreviewToken !== token) return;
        if (result && result.ok && result.outputFile) {
          cfg.outputFileManual = false;
          cfg.outputFile = result.outputFile;
          cfg.outputAutoUrl = url;
          this.updateFilePicker('nsOutput', result.outputFile, '自动生成 / 选择文件');
          await this.persistPageConfig('web_crawler');
        }
      } catch (error) {
        console.debug('web crawler preview failed', error);
      }
    },
  };
})();
