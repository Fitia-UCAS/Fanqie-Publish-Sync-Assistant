window.renderCharacterMaterialPage = function renderCharacterMaterialPage(app) {
  const cfg = app.state.config.character_material || {};
  const platforms = app.state.characterMaterialPlatforms || {};
  const defaults = (app.state.characterMaterialDefaults || {})[cfg.platform || 'deepseek'] || {};
  const platformOptions = Object.entries(platforms).map(([key, label]) => `<option value="${app.attr(key)}" ${String(cfg.platform || 'deepseek') === key ? 'selected' : ''}>${app.escape(label)}</option>`).join('');
  const baseUrl = cfg.baseUrl || defaults.baseUrl || '';
  const modelName = cfg.modelName || defaults.modelName || '';
  return `
    <section class="page active" data-page="character_material">
      <div class="fanqie-task-grid">
        <div class="fanqie-settings-card">
          <div class="settings-body">
            <div class="form-grid">
              <div class="field">
                <label>小说 TXT</label>
                ${app.filePicker('cmSource', cfg.source || '', 'cmChooseSource', '选择完整小说 TXT')}
              </div>
              <div class="field">
                <label>输出目录</label>
                ${app.filePicker('cmOutputDir', cfg.outputDir || '', 'cmChooseOutputDir', '自动生成 / 选择目录')}
              </div>
              <div class="field"><label>模型平台</label><select class="select" id="cmPlatform">${platformOptions}</select></div>
              <div class="field"><label>API Key</label><input class="input" id="cmApiKey" type="password" value="${app.attr(cfg.apiKey || '')}" placeholder="可留空，读取环境变量" /></div>
              <div class="field"><label>Base URL</label><input class="input" id="cmBaseUrl" value="${app.attr(baseUrl)}" placeholder="OpenAI 兼容接口地址" /></div>
              <div class="field-pair">
                <div class="field"><label>模型名称</label><input class="input" id="cmModelName" value="${app.attr(modelName)}" placeholder="deepseek-chat / gpt-4o-mini" /></div>
                <div class="field"><label>温度</label><input class="input" id="cmTemperature" type="number" min="0" max="2" step="0.1" value="${app.attr(cfg.temperature ?? 0.2)}" /></div>
              </div>
              <div class="field-pair">
                <div class="field"><label>人物 / 对象</label><input class="input" id="cmCharacterTarget" value="${app.attr(cfg.characterTarget || '')}" placeholder="可空，如：林恒 / 云瑶 / 环境 / 所有人物" /></div>
                <div class="field"><label>关键词</label><input class="input" id="cmKeyword" value="${app.attr(cfg.keyword || '')}" placeholder="完全自由输入，如：嚣张语气对话 / 吃醋嘴硬 / 打斗动作 / 景色氛围" /></div>
              </div>
              <div class="field-pair">
                <div class="field"><label>单章</label><input class="input" id="cmChapter" type="number" min="1" value="${app.attr(cfg.chapter || '')}" placeholder="可空" /></div>
                <div class="field"><label>并发数</label><input class="input" id="cmWorkers" type="number" min="1" max="16" value="${app.attr(cfg.maxWorkers || 4)}" /></div>
              </div>
              <div class="field-pair">
                <div class="field"><label>起始章</label><input class="input" id="cmStart" type="number" min="1" value="${app.attr(cfg.start || '')}" placeholder="可空" /></div>
                <div class="field"><label>结束章</label><input class="input" id="cmEnd" type="number" min="1" value="${app.attr(cfg.end || '')}" placeholder="可空" /></div>
              </div>
              <div class="option-grid two-col">
                <label><input type="checkbox" id="cmAll" ${cfg.allChapters !== false ? 'checked' : ''}/> 全部章节</label>
                <label><input type="checkbox" id="cmConcurrent" ${cfg.concurrent !== false ? 'checked' : ''}/> 并发抽取</label>
                <label><input type="checkbox" checked disabled/> 按每章抽取</label>
                <label><input type="checkbox" checked disabled/> JSONL 输出</label>
              </div>
              <div class="action-row two-actions compact-actions">
                <button class="big-action primary-action" id="cmRun" type="button"><span>◆</span><div><b>开始抽取</b></div></button>
                <button class="big-action primary-action" id="cmStop" type="button"><span>×</span><div><b>停止抽取</b></div></button>
              </div>
            </div>
          </div>
        </div>
        ${app.renderTerminalPanel('character_material')}
      </div>
    </section>
  `;
};
