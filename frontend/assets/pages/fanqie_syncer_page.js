window.renderFanqieSyncerPage = function renderFanqieSyncerPage(app) {
  const cfg = app.state.config.chapter_sync || {};
  return `
    <section class="page active" data-page="chapter_sync">
      <div class="fanqie-task-grid">
        <div class="fanqie-settings-card">
          <div class="settings-body">
            <div class="form-grid fanqie-form">
              <div class="field">
                <label>小说来源</label>
                ${app.filePicker('syNovelFile', cfg.novelFile || '', 'syChooseNovel', '选择小说来源')}
              </div>
              <div class="field">
                <label>章节管理 URL</label>
                <input class="input" id="syUrl" value="${app.attr(cfg.chapterManageUrl || '')}" placeholder="https://fanqienovel.com/..." />
              </div>
              ${app.renderFanqieLoginStateRow ? app.renderFanqieLoginStateRow('sy', cfg) : ''}
              <div class="field-pair">
                <div class="field"><label>起始章节</label><input class="input" id="syStart" type="number" min="1" value="${app.attr(cfg.start || 1)}" /></div>
                <div class="field"><label>结束章节</label><input class="input" id="syEnd" type="number" min="1" value="${app.attr(cfg.end || 1)}" /></div>
              </div>
              <div class="group-label">同步选项</div>
              <div class="option-grid two-col fanqie-option-grid">
                <label><input type="checkbox" id="syUseAi" ${cfg.useAi ? 'checked' : ''}/> 使用 AI</label>
                <label><input type="checkbox" id="syVerifyAfterPublish" ${cfg.verifyAfterPublish !== false ? 'checked' : ''}/> 列表校验</label>
                <label><input type="checkbox" id="syHeadless" ${cfg.headless ? 'checked' : ''}/> 后台无头</label>
                <label><input type="checkbox" id="syDebugScreenshots" ${cfg.debugScreenshots !== false ? 'checked' : ''}/> 步骤截图</label>
                <label><input type="checkbox" id="syFailureScreenshots" ${cfg.failureScreenshots !== false ? 'checked' : ''}/> 失败截图</label>
                <label><input type="checkbox" id="syGitTracking" ${cfg.gitTracking !== false ? 'checked' : ''}/> Git追踪</label>
                <label><input type="checkbox" id="syCleanBeforeRun" ${cfg.cleanBeforeRun !== false ? 'checked' : ''}/> 启动清理</label>
              </div>
              <div class="group-label">执行操作</div>
              <div class="action-stack fanqie-actions">
                <div class="action-row two-actions">
                  <button class="big-action primary-action" data-sync-op="publish"><span>↻</span><div><b>开始同步</b></div></button>
                  <button class="big-action primary-action" id="syStop" type="button"><span>×</span><div><b>停止同步</b></div></button>
                </div>
                <div class="action-row two-actions">
                  <button class="big-action primary-action" id="syPause" type="button"><span>⏸</span><div><b>暂停</b></div></button>
                  <button class="big-action primary-action" id="syResume" type="button"><span>▶</span><div><b>继续</b></div></button>
                </div>
                <div class="action-row two-actions">
                  <button class="big-action primary-action" data-sync-op="pull"><span>↓</span><div><b>开始拉取</b></div></button>
                  <button class="big-action primary-action" data-sync-op="compare"><span>≠</span><div><b>打开对比</b></div></button>
                </div>
              </div>
            </div>
          </div>
        </div>
        ${app.renderTerminalPanel('chapter_sync')}
      </div>
    </section>
  `;
};
