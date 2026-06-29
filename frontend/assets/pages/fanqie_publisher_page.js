window.renderFanqiePublisherPage = function renderFanqiePublisherPage(app) {
  const cfg = app.state.config.auto_publish || {};
  return `
    <section class="page active" data-page="auto_publish">
      <div class="fanqie-task-grid">
        <div class="fanqie-settings-card">
          <div class="settings-body">
            <div class="form-grid fanqie-form">
              <div class="field">
                <label>小说来源</label>
                ${app.filePicker('apNovelFile', cfg.novelFile || '', 'apChooseNovel', '选择小说来源')}
              </div>
              <div class="field">
                <label>章节管理 URL</label>
                <input class="input" id="apUrl" value="${app.attr(cfg.chapterManageUrl || '')}" placeholder="https://fanqienovel.com/..." />
              </div>
              ${app.renderFanqieLoginStateRow ? app.renderFanqieLoginStateRow('ap', cfg) : ''}
              <div class="field-pair">
                <div class="field"><label>起始章节</label><input class="input" id="apStart" type="number" min="1" value="${app.attr(cfg.start || 1)}" /></div>
                <div class="field"><label>结束章节</label><input class="input" id="apEnd" type="number" min="1" value="${app.attr(cfg.end || 1)}" /></div>
              </div>
              <div class="group-label">发布选项</div>
              <div class="option-grid two-col fanqie-option-grid">
                <label><input type="checkbox" id="apUseAi" ${cfg.useAi ? 'checked' : ''}/> 使用 AI</label>
                <label><input type="checkbox" id="apVerifyAfterPublish" ${cfg.verifyAfterPublish !== false ? 'checked' : ''}/> 列表校验</label>
                <label><input type="checkbox" id="apHeadless" ${cfg.headless ? 'checked' : ''}/> 后台无头</label>
                <label><input type="checkbox" id="apDebugScreenshots" ${cfg.debugScreenshots !== false ? 'checked' : ''}/> 步骤截图</label>
                <label><input type="checkbox" id="apFailureScreenshots" ${cfg.failureScreenshots !== false ? 'checked' : ''}/> 失败截图</label>
                <label><input type="checkbox" id="apGitTracking" ${cfg.gitTracking !== false ? 'checked' : ''}/> Git追踪</label>
                <label><input type="checkbox" id="apCleanBeforeRun" ${cfg.cleanBeforeRun !== false ? 'checked' : ''}/> 启动清理</label>
                <label><input type="checkbox" id="apManualSchedule" ${cfg.manualSchedule ? 'checked' : ''}/> 手动定时</label>
              </div>
              <div class="manual-schedule-fields ${cfg.manualSchedule ? '' : 'hidden'}" id="apManualScheduleFields">
                <div class="field schedule-date-field"><label>起始日期</label><input class="input" id="apScheduleStartDate" type="date" value="${app.attr(cfg.scheduleStartDate || '')}" /></div>
                <div class="schedule-time-grid">
                  <div class="field"><label>上午时间</label><input class="input" id="apScheduleMorningTime" type="time" value="${app.attr(cfg.scheduleMorningTime || '10:00')}" /></div>
                  <div class="field"><label>上午章数</label><input class="input" id="apScheduleMorningCount" type="number" min="0" value="${app.attr(cfg.scheduleMorningCount || 1)}" /></div>
                  <div class="field"><label>下午时间</label><input class="input" id="apScheduleAfternoonTime" type="time" value="${app.attr(cfg.scheduleAfternoonTime || '18:00')}" /></div>
                  <div class="field"><label>下午章数</label><input class="input" id="apScheduleAfternoonCount" type="number" min="0" value="${app.attr(cfg.scheduleAfternoonCount || 0)}" /></div>
                </div>
              </div>
              <div class="group-label">执行操作</div>
              <div class="action-stack fanqie-actions">
                <div class="action-row two-actions">
                  <button class="big-action primary-action" data-auto-op="publish"><span>↑</span><div><b>启动发布</b></div></button>
                  <button class="big-action primary-action" id="apStop" type="button"><span>×</span><div><b>停止发布</b></div></button>
                </div>
                <div class="action-row two-actions">
                  <button class="big-action primary-action" id="apPause" type="button"><span>⏸</span><div><b>暂停</b></div></button>
                  <button class="big-action primary-action" id="apResume" type="button"><span>▶</span><div><b>继续</b></div></button>
                </div>
              </div>
            </div>
          </div>
        </div>
        ${app.renderTerminalPanel('auto_publish')}
      </div>
    </section>
  `;
};
