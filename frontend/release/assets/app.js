(() => {
  const $ = (id) => document.getElementById(id);
  const PATH_FIELDS = new Set(['apNovelFile', 'syNovelFile', 'authStatePath']);
  const SCHEDULE_DEBOUNCE = 600;
  const FORM_SECTIONS = { ap: 'auto_publish', sy: 'chapter_sync' };
  const pageNames = { auto_publish: '番茄发布', chapter_sync: '番茄同步', system: '系统' };
  const consoleOutput = $('consoleOutput');
  let state = { config: {} };
  let saveTimer = null;

  const baseName = (value) => {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const parts = raw.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    if (parts.length > 1) return `${parts.length} 项已选择`;
    return parts[0].split(/[\\/]/).filter(Boolean).pop() || raw;
  };
  const val = (id) => {
    const node = $(id);
    if (!node) return '';
    const raw = node.dataset.fullValue || '';
    return (raw && node.value === baseName(raw)) ? raw.trim() : String(node.value || '').trim();
  };
  const num = (id, fallback = 0) => Number(val(id) || fallback);
  const checked = (id) => !!$(id)?.checked;
  const setVal = (id, value) => {
    const node = $(id);
    if (!node || value === undefined || value === null) return;
    const raw = String(value || '');
    if (PATH_FIELDS.has(id)) {
      node.dataset.fullValue = raw;
      node.value = baseName(raw);
      node.title = raw;
      return;
    }
    node.value = raw;
    node.removeAttribute('title');
  };
  const setChecked = (id, value) => { const node = $(id); if (node) node.checked = !!value; };
  const api = () => window.pywebview && window.pywebview.api;
  const stamp = () => new Date().toLocaleTimeString();
  const lineText = (message, level = 'info', page = '') => {
    const text = String(message || '').trim() || '完成。';
    const label = page ? `${pageNames[page] || page} ` : '';
    return `[${stamp()}] ${String(level || 'info').toUpperCase()} ${label}${text}`;
  };
  const log = (message, level = 'info', page = '') => {
    if (!consoleOutput) return;
    consoleOutput.textContent += `${consoleOutput.textContent ? '\n' : ''}${lineText(message, level, page)}`;
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
  };
  const replaceConsole = (text) => {
    if (!consoleOutput) return;
    consoleOutput.textContent = String(text || '').trim();
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
  };
  const callApi = async (name, ...args) => {
    if (!api() || typeof api()[name] !== 'function') throw new Error('未连接后端，部分功能不可用');
    return api()[name](...args);
  };
  const mergeDeep = (target, source) => {
    const output = Object.assign({}, target || {});
    Object.entries(source || {}).forEach(([key, value]) => {
      if (value && typeof value === 'object' && !Array.isArray(value)) output[key] = mergeDeep(output[key] || {}, value);
      else output[key] = value;
    });
    return output;
  };
  const saveConfig = async (patch) => {
    state.config = mergeDeep(state.config || {}, patch || {});
    await callApi('save_config', patch || {});
  };
  const setStyle = (style) => {
    document.body.dataset.style = style;
    localStorage.setItem('fanqieUiTheme', style);
    document.querySelectorAll('[data-theme-style]').forEach((button) => button.classList.toggle('active', button.dataset.themeStyle === style));
  };
  const setView = (view) => {
    if (!['publish', 'sync'].includes(view)) view = 'publish';
    document.body.dataset.currentView = view;
    document.querySelectorAll('[data-view]').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
    saveConfig({ activePage: view === 'sync' ? 'chapter_sync' : 'auto_publish' }).catch(() => {});
  };
  const syncScheduleBox = (prefix) => $(`${prefix}ManualScheduleFields`)?.classList.toggle('hidden', !checked(`${prefix}ManualSchedule`));
  const collectPublishPayload = (prefix, operation) => ({
    novelFile: val(`${prefix}NovelFile`),
    chapterManageUrl: val(`${prefix}Url`),
    authStatePath: val('authStatePath'),
    start: num(`${prefix}Start`, 1),
    end: num(`${prefix}End`, 1),
    useAi: checked(`${prefix}UseAi`),
    verifyAfterPublish: checked(`${prefix}VerifyAfterPublish`),
    debugScreenshots: checked(`${prefix}DebugScreenshots`),
    failureScreenshots: checked(`${prefix}FailureScreenshots`),
    gitTracking: checked(`${prefix}GitTracking`),
    cleanBeforeRun: checked(`${prefix}CleanBeforeRun`),
    headless: checked(`${prefix}Headless`),
    manualSchedule: checked(`${prefix}ManualSchedule`),
    scheduleStartDate: val(`${prefix}ScheduleStartDate`),
    scheduleMorningTime: val(`${prefix}ScheduleMorningTime`) || '10:00',
    scheduleMorningCount: num(`${prefix}ScheduleMorningCount`, 1),
    scheduleAfternoonTime: val(`${prefix}ScheduleAfternoonTime`) || '18:00',
    scheduleAfternoonCount: num(`${prefix}ScheduleAfternoonCount`, 0),
    operation,
  });
  const saveSharedAuthPath = (path = val('authStatePath')) => saveConfig({
    auto_publish: { authStatePath: path },
    chapter_sync: { authStatePath: path },
  });
  const fillFromState = (nextState) => {
    state = nextState || { config: {} };
    const config = state.config || {};
    const ap = config.auto_publish || {};
    const sy = config.chapter_sync || {};

    setVal('authStatePath', ap.authStatePath || sy.authStatePath || '');
    setVal('apNovelFile', ap.novelFile || ''); setVal('apUrl', ap.chapterManageUrl || '');
    setVal('apStart', ap.start || 1); setVal('apEnd', ap.end || 1);
    setChecked('apUseAi', ap.useAi); setChecked('apVerifyAfterPublish', ap.verifyAfterPublish !== false); setChecked('apHeadless', ap.headless);
    setChecked('apDebugScreenshots', ap.debugScreenshots !== false); setChecked('apFailureScreenshots', ap.failureScreenshots !== false); setChecked('apGitTracking', ap.gitTracking !== false);
    setChecked('apCleanBeforeRun', ap.cleanBeforeRun !== false); setChecked('apManualSchedule', ap.manualSchedule);
    setVal('apScheduleStartDate', ap.scheduleStartDate || ''); setVal('apScheduleMorningTime', ap.scheduleMorningTime || '10:00'); setVal('apScheduleMorningCount', ap.scheduleMorningCount ?? 1);
    setVal('apScheduleAfternoonTime', ap.scheduleAfternoonTime || '18:00'); setVal('apScheduleAfternoonCount', ap.scheduleAfternoonCount ?? 0);
    syncScheduleBox('ap');

    setVal('syNovelFile', sy.novelFile || ''); setVal('syUrl', sy.chapterManageUrl || '');
    setVal('syStart', sy.start || 1); setVal('syEnd', sy.end || 1);
    setChecked('syUseAi', sy.useAi); setChecked('syVerifyAfterPublish', sy.verifyAfterPublish !== false); setChecked('syHeadless', sy.headless);
    setChecked('syDebugScreenshots', sy.debugScreenshots !== false); setChecked('syFailureScreenshots', sy.failureScreenshots !== false); setChecked('syGitTracking', sy.gitTracking !== false);
    setChecked('syCleanBeforeRun', sy.cleanBeforeRun !== false); setChecked('syManualSchedule', sy.manualSchedule);
    setVal('syScheduleStartDate', sy.scheduleStartDate || ''); setVal('syScheduleMorningTime', sy.scheduleMorningTime || '10:00'); setVal('syScheduleMorningCount', sy.scheduleMorningCount ?? 1);
    setVal('syScheduleAfternoonTime', sy.scheduleAfternoonTime || '18:00'); setVal('syScheduleAfternoonCount', sy.scheduleAfternoonCount ?? 0);
    syncScheduleBox('sy');

    if (state.logTail && !consoleOutput.textContent.trim()) replaceConsole(state.logTail);
  };
  const updateLoginStatus = async () => {
    try {
      const loggedIn = await callApi('check_login_state');
      log(loggedIn ? '检测到有效的 state.json，已登录。' : '未检测到 state.json，需要登录。', loggedIn ? 'success' : 'warn');
    } catch { }
  };
  const refresh = async () => {
    try {
      fillFromState(await callApi('get_state'));
      if (!consoleOutput.textContent.trim()) replaceConsole('已连接后端，等待任务日志。');
      updateLoginStatus();
    } catch (error) {
      replaceConsole(lineText(error.message, 'warn'));
    }
  };

  window.NovelTools = {
    appendLog(page, message, level = 'info') { log(message, level, page); },
    applyTaskEvent(event) { log(event?.displayMessage || event?.message || '', event?.level || 'info', event?.page || ''); },
    setProgress(page, current, total) { log(`进度：${current}/${total}`, 'info', page); },
    taskDone(page, ok, result) { log(result?.message || (ok ? '任务完成。' : '任务失败。'), ok ? 'success' : 'error', page); },
  };

  document.querySelectorAll('[data-theme-style]').forEach((button) => button.addEventListener('click', () => setStyle(button.dataset.themeStyle)));
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
  $('clearConsole')?.addEventListener('click', () => replaceConsole(''));
  $('copyConsole')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(consoleOutput.textContent || ''); log('运行日志已复制。', 'success'); }
    catch { log('复制失败，请手动选择日志内容。', 'warn'); }
  });
  $('apManualSchedule')?.addEventListener('change', () => syncScheduleBox('ap'));
  $('syManualSchedule')?.addEventListener('change', () => syncScheduleBox('sy'));
  $('authStatePath')?.addEventListener('input', () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveSharedAuthPath().catch(() => {}), SCHEDULE_DEBOUNCE);
  });
  PATH_FIELDS.forEach((id) => {
    const node = $(id);
    node?.addEventListener('input', () => { delete node.dataset.fullValue; node.removeAttribute('title'); });
  });

  document.querySelectorAll('[data-choose]').forEach((button) => button.addEventListener('click', async () => {
    try {
      const kind = button.dataset.choose;
      const target = button.dataset.target;
      const config = button.dataset.config || '';
      let path = '';
      if (kind === 'source') path = await (api()?.choose_source ? callApi('choose_source', config) : callApi('choose_file', config, false, 'novel.txt'));
      else if (kind === 'auth') path = await (api()?.choose_login_state ? callApi('choose_login_state', config) : callApi('choose_file', config, false, 'state.json'));
      else path = await callApi('choose_file', config, false, 'novel.txt');
      if (path && target) {
        setVal(target, path);
        if (target === 'authStatePath') await saveSharedAuthPath(path);
      }
    } catch (error) { log(error.message, 'error'); }
  }));

  document.querySelectorAll('[data-run]').forEach((button) => button.addEventListener('click', async () => {
    try {
      const run = button.dataset.run;
      if (run === 'auto_publish') {
        const payload = collectPublishPayload('ap', button.dataset.operation || 'publish');
        await saveConfig({ auto_publish: payload });
        log(await callApi('auto_publish_run', payload) ? '番茄发布任务已启动。' : '番茄发布任务未启动。', 'success');
      } else if (run === 'chapter_sync') {
        const payload = collectPublishPayload('sy', button.dataset.operation || 'push');
        await saveConfig({ chapter_sync: payload });
        log(await callApi('chapter_sync_run', payload) ? '番茄同步任务已启动。' : '番茄同步任务未启动。', 'success');
      } else if (run === 'do_login') {
        await callApi('do_login');
      } else if (run === 'check_login_state') {
        updateLoginStatus();
        log('登录状态已检测。', 'success');
      } else if (run === 'reset_login') {
        const result = await callApi('reset_login');
        updateLoginStatus();
        log(result?.message || '已重置登录授权。', 'warning');
      } else {
        const ok = await callApi(run);
        log(ok ? '操作已提交。' : '当前没有可处理任务。', ok ? 'success' : 'warn');
      }
    } catch (error) { log(error.message, 'error'); }
  }));

  document.querySelectorAll('[data-panel="publish"] input, [data-panel="publish"] select, [data-panel="sync"] input, [data-panel="sync"] select').forEach((el) => {
    const id = el.id;
    const prefix = id && id.match(/^(ap|sy)/)?.[1];
    if (!prefix) return;
    const section = FORM_SECTIONS[prefix];
    const persist = () => {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        const payload = collectPublishPayload(prefix, $(`${prefix}Operation`)?.value || (prefix === 'sy' ? 'push' : 'publish'));
        saveConfig({ [section]: payload }).catch(() => {});
      }, SCHEDULE_DEBOUNCE);
    };
    el.addEventListener('input', persist);
    el.addEventListener('change', persist);
  });

  setStyle(['pixel', 'night'].includes(localStorage.getItem('fanqieUiTheme')) ? localStorage.getItem('fanqieUiTheme') : 'pixel');
  setView('publish');
  refresh();
})();
