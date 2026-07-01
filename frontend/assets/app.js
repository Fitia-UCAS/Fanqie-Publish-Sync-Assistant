(() => {
  const $ = (id) => document.getElementById(id);
  const PATH_FIELDS = new Set([
    'apNovelFile', 'apAuthStatePath', 'syNovelFile', 'syAuthStatePath',
    'exNovelFile', 'exOutputFile', 'exBatchFolder', 'spInputFile', 'spOutputDir',
    'tcAdInput', 'tcAdFolder', 'tcMoveInput', 'tcMoveFolder', 'nsOutput',
    'cmSource', 'cmOutputDir', 'cpSource', 'cpCurrentPlotFile', 'cpOutputDir', 'cpOutputFile'
  ]);
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
    } else {
      node.value = raw;
      node.removeAttribute('title');
    }
  };
  const setChecked = (id, value) => { const node = $(id); if (node) node.checked = !!value; };
  const consoleOutput = $('consoleOutput');
  let state = { config: {} };

  const pageNames = {
    auto_publish: '番茄发布', chapter_sync: '番茄同步', process_novel: '小说处理', process_novel_batch: '批量格式化',
    novel_splitter: '小说分割', clean_text_ads: '清理广告', clean_text_breaks: '修复句子', web_crawler: '网页抓取',
    character_material: '角色素材', current_plot: '当前剧情', system: '系统'
  };
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
  const setStyle = (style) => {
    document.body.dataset.style = style;
    localStorage.setItem('fanqieUiTheme', style);
    document.querySelectorAll('[data-theme-style]').forEach((button) => button.classList.toggle('active', button.dataset.themeStyle === style));
  };
  const setView = (view) => {
    document.body.dataset.currentView = view;
    document.querySelectorAll('[data-view]').forEach((button) => button.classList.toggle('active', button.dataset.view === view));
    saveConfig({ activePage: ({ publish: 'auto_publish', sync: 'chapter_sync', process: 'process_novel', crawler: 'web_crawler' }[view] || view) }).catch(() => {});
  };
  const saveConfig = async (patch) => {
    state.config = mergeDeep(state.config || {}, patch || {});
    await callApi('save_config', patch || {});
  };
  const mergeDeep = (target, source) => {
    const output = Object.assign({}, target || {});
    Object.entries(source || {}).forEach(([key, value]) => {
      if (value && typeof value === 'object' && !Array.isArray(value)) output[key] = mergeDeep(output[key] || {}, value);
      else output[key] = value;
    });
    return output;
  };
  const optionList = (selectId, items, current) => {
    const select = $(selectId);
    if (!select || !items || !Object.keys(items).length) return;
    select.innerHTML = Object.entries(items).map(([key, label]) => `<option value="${key}">${label}</option>`).join('');
    if (current) select.value = current;
  };
  const fillFromState = (nextState) => {
    state = nextState || { config: {} };
    const config = state.config || {};
    const ap = config.auto_publish || {};
    const sy = config.chapter_sync || {};
    const pn = config.process_novel || {};
    const split = config.novel_splitter || {};
    const clean = config.clean_text || {};
    const wc = config.web_crawler || {};
    const cm = config.character_material || {};
    const cp = config.current_plot || {};

    setVal('apNovelFile', ap.novelFile || ''); setVal('apUrl', ap.chapterManageUrl || ''); setVal('apAuthStatePath', ap.authStatePath || '');
    setVal('apStart', ap.start || 1); setVal('apEnd', ap.end || 1);
    setChecked('apUseAi', ap.useAi); setChecked('apVerifyAfterPublish', ap.verifyAfterPublish !== false); setChecked('apHeadless', ap.headless);
    setChecked('apDebugScreenshots', ap.debugScreenshots !== false); setChecked('apFailureScreenshots', ap.failureScreenshots !== false); setChecked('apGitTracking', ap.gitTracking !== false);
    setChecked('apCleanBeforeRun', ap.cleanBeforeRun !== false); setChecked('apManualSchedule', ap.manualSchedule);
    setVal('apScheduleStartDate', ap.scheduleStartDate || ''); setVal('apScheduleMorningTime', ap.scheduleMorningTime || '10:00'); setVal('apScheduleMorningCount', ap.scheduleMorningCount ?? 1);
    setVal('apScheduleAfternoonTime', ap.scheduleAfternoonTime || '18:00'); setVal('apScheduleAfternoonCount', ap.scheduleAfternoonCount ?? 0);
    syncScheduleBox('ap');

    setVal('syNovelFile', sy.novelFile || ''); setVal('syUrl', sy.chapterManageUrl || ''); setVal('syAuthStatePath', sy.authStatePath || '');
    setVal('syStart', sy.start || 1); setVal('syEnd', sy.end || 1);
    setChecked('syUseAi', sy.useAi); setChecked('syVerifyAfterPublish', sy.verifyAfterPublish !== false); setChecked('syHeadless', sy.headless);
    setChecked('syDebugScreenshots', sy.debugScreenshots !== false); setChecked('syFailureScreenshots', sy.failureScreenshots !== false); setChecked('syGitTracking', sy.gitTracking !== false);
    setChecked('syCleanBeforeRun', sy.cleanBeforeRun !== false); setChecked('syManualSchedule', sy.manualSchedule);
    setVal('syScheduleStartDate', sy.scheduleStartDate || ''); setVal('syScheduleMorningTime', sy.scheduleMorningTime || '10:00'); setVal('syScheduleMorningCount', sy.scheduleMorningCount ?? 1);
    setVal('syScheduleAfternoonTime', sy.scheduleAfternoonTime || '18:00'); setVal('syScheduleAfternoonCount', sy.scheduleAfternoonCount ?? 0);
    syncScheduleBox('sy');

    setVal('exNovelFile', pn.novelFile || clean.inputFile || ''); setVal('exOutputFile', pn.outputFile || ''); setVal('exBatchFolder', pn.batchFolder || clean.batchFolder || '');
    setVal('exChapter', pn.chapter || ''); setVal('exAroundChapter', pn.aroundChapter || ''); setVal('exStart', pn.start || ''); setVal('exEnd', pn.end || ''); setChecked('exBackup', pn.backup !== false);
    setVal('spInputFile', split.inputFile || pn.novelFile || ''); setVal('spOutputDir', split.outputDir || ''); setVal('spMode', split.splitMode || 'chapter_count');
    setVal('spChaptersPerFile', split.chaptersPerFile || 10); setVal('spMaxSizeMb', split.maxSizeMb || 5); setChecked('spIncludePrelude', split.includePrelude !== false); setChecked('spCleanOutput', split.cleanOutput);
    setVal('tcAdInput', clean.adInputFile || clean.inputFile || pn.novelFile || ''); setVal('tcAdFolder', clean.adBatchFolder || clean.batchFolder || pn.batchFolder || ''); setVal('tcAdProfile', clean.adProfile || 'mimiread');
    setChecked('tcAdOverwrite', clean.overwrite !== false); setChecked('tcAdBackup', clean.backup !== false);
    setVal('tcMoveInput', clean.moveInputFile || clean.inputFile || pn.novelFile || ''); setVal('tcMoveFolder', clean.moveBatchFolder || clean.batchFolder || pn.batchFolder || '');
    setVal('tcMaxMoveChars', clean.maxMoveChars || 120); setVal('tcMovePunctuation', clean.normalizePunctuation === false ? 'off' : 'on');
    setChecked('tcMoveOverwrite', clean.overwrite !== false); setChecked('tcMoveBackup', clean.backup !== false);
    const profiles = state.adProfiles || [];
    if (profiles.length) optionList('tcAdProfile', Object.fromEntries(profiles.map((p) => [p.key, p.name])), clean.adProfile || 'mimiread');

    setVal('nsUrl', wc.novelUrl || ''); setVal('nsOutput', wc.outputFile || ''); setVal('nsStart', wc.start || 1); setVal('nsEnd', wc.end || '');
    setVal('nsWorkers', wc.maxWorkers || 16); setVal('nsTimeout', wc.timeout || 25); setVal('nsDelayMin', wc.requestDelayMin ?? 0.12); setVal('nsDelayMax', wc.requestDelayMax ?? 0.35); setVal('nsRetries', wc.maxRetries ?? 3);
    setChecked('nsHtmlFallback', wc.htmlFallback !== false); setChecked('nsDetailedLog', wc.detailedLog);

    optionList('cmPlatform', state.characterMaterialPlatforms, cm.platform || 'deepseek');
    const cmDefaults = (state.characterMaterialDefaults || {})[cm.platform || 'deepseek'] || {};
    setVal('cmSource', cm.source || ''); setVal('cmOutputDir', cm.outputDir || ''); setVal('cmApiKey', cm.apiKey || '');
    setVal('cmBaseUrl', cm.baseUrl || cmDefaults.baseUrl || ''); setVal('cmModelName', cm.modelName || cmDefaults.modelName || ''); setVal('cmTemperature', cm.temperature ?? 0.2);
    setVal('cmCharacterTarget', cm.characterTarget || ''); setVal('cmKeyword', cm.keyword || ''); setVal('cmChapter', cm.chapter || '');
    setVal('cmStart', cm.start || ''); setVal('cmEnd', cm.end || ''); setVal('cmWorkers', cm.maxWorkers || 4);
    setChecked('cmAll', cm.allChapters !== false); setChecked('cmConcurrent', cm.concurrent !== false);

    optionList('cpPlatform', state.currentPlotPlatforms || state.characterMaterialPlatforms, cp.platform || 'deepseek');
    const cpDefaults = (state.currentPlotDefaults || state.characterMaterialDefaults || {})[cp.platform || 'deepseek'] || {};
    setVal('cpSource', cp.source || ''); setVal('cpCurrentPlotFile', cp.currentPlotFile || ''); setVal('cpOutputDir', cp.outputDir || ''); setVal('cpOutputFile', cp.outputFile || '');
    setVal('cpApiKey', cp.apiKey || ''); setVal('cpBaseUrl', cp.baseUrl || cpDefaults.baseUrl || ''); setVal('cpModelName', cp.modelName || cpDefaults.modelName || ''); setVal('cpTemperature', cp.temperature ?? 0.2);
    setVal('cpChapter', cp.chapter || ''); setVal('cpAroundChapter', cp.aroundChapter || ''); setVal('cpStart', cp.start || ''); setVal('cpEnd', cp.end || '');
    setVal('cpMode', cp.mode || 'extract_merge'); setVal('cpTargetWords', cp.targetWords || 260); setVal('cpRecentContext', cp.recentContextCount ?? 5); setVal('cpWorkers', cp.maxWorkers || 4);
    setChecked('cpReplaceExisting', cp.replaceExisting !== false);

    if (state.logTail && !consoleOutput.textContent.trim()) replaceConsole(state.logTail);
  };
  const refresh = async () => {
    try {
      fillFromState(await callApi('get_state'));
      if (!consoleOutput.textContent.trim()) replaceConsole('已连接后端，等待任务日志。');
    } catch (error) {
      replaceConsole(lineText(error.message, 'warn'));
    }
  };
  const syncScheduleBox = (prefix = 'ap') => $(`${prefix}ManualScheduleFields`)?.classList.toggle('hidden', !checked(`${prefix}ManualSchedule`));

  const collectPublishPayload = (prefix, operation) => ({
    novelFile: val(`${prefix}NovelFile`), chapterManageUrl: val(`${prefix}Url`), authStatePath: val(`${prefix}AuthStatePath`),
    start: num(`${prefix}Start`, 1), end: num(`${prefix}End`, 1), useAi: checked(`${prefix}UseAi`), verifyAfterPublish: checked(`${prefix}VerifyAfterPublish`),
    debugScreenshots: checked(`${prefix}DebugScreenshots`), failureScreenshots: checked(`${prefix}FailureScreenshots`), gitTracking: checked(`${prefix}GitTracking`),
    cleanBeforeRun: checked(`${prefix}CleanBeforeRun`), headless: checked(`${prefix}Headless`), manualSchedule: checked(`${prefix}ManualSchedule`),
    scheduleStartDate: val(`${prefix}ScheduleStartDate`), scheduleMorningTime: val(`${prefix}ScheduleMorningTime`) || '10:00', scheduleMorningCount: num(`${prefix}ScheduleMorningCount`, 1),
    scheduleAfternoonTime: val(`${prefix}ScheduleAfternoonTime`) || '18:00', scheduleAfternoonCount: num(`${prefix}ScheduleAfternoonCount`, 0), operation,
  });
  const collectProcessPayload = (mode, logTarget = 'process_novel') => ({
    novelFile: val('exNovelFile'), batchFolder: val('exBatchFolder'), outputFile: val('exOutputFile'), chapter: num('exChapter'), aroundChapter: num('exAroundChapter'), start: num('exStart'), end: num('exEnd'), backup: checked('exBackup'), mode, logTarget
  });
  const collectNovelSplitPayload = () => ({
    inputFile: val('spInputFile'), outputDir: val('spOutputDir'), splitMode: val('spMode') || 'chapter_count', chaptersPerFile: num('spChaptersPerFile', 10), maxSizeMb: Number(val('spMaxSizeMb') || 5), includePrelude: checked('spIncludePrelude'), cleanOutput: checked('spCleanOutput')
  });
  const collectCleanTextPayload = (scope) => {
    const isMove = scope === 'move';
    const shared = { adInputFile: val('tcAdInput'), adBatchFolder: val('tcAdFolder'), moveInputFile: val('tcMoveInput'), moveBatchFolder: val('tcMoveFolder'), adProfile: val('tcAdProfile') || 'mimiread', normalizePunctuation: val('tcMovePunctuation') !== 'off', maxMoveChars: num('tcMaxMoveChars', 120) };
    return Object.assign(shared, {
      scope,
      inputFile: isMove ? val('tcMoveInput') : val('tcAdInput'),
      batchFolder: isMove ? val('tcMoveFolder') : val('tcAdFolder'),
      overwrite: isMove ? checked('tcMoveOverwrite') : checked('tcAdOverwrite'),
      backup: isMove ? checked('tcMoveBackup') : checked('tcAdBackup'),
    });
  };
  const collectCrawlerPayload = () => ({
    novelUrl: val('nsUrl'), outputFile: val('nsOutput'), start: num('nsStart', 1), end: num('nsEnd'), maxWorkers: num('nsWorkers', 16), timeout: num('nsTimeout', 25),
    requestDelayMin: Number(val('nsDelayMin') || 0.12), requestDelayMax: Number(val('nsDelayMax') || 0.35), maxRetries: num('nsRetries', 3), htmlFallback: checked('nsHtmlFallback'), detailedLog: checked('nsDetailedLog')
  });
  const collectCharacterPayload = () => ({
    source: val('cmSource'), outputDir: val('cmOutputDir'), platform: val('cmPlatform') || 'deepseek', apiKey: val('cmApiKey'), baseUrl: val('cmBaseUrl'), modelName: val('cmModelName'), temperature: Number(val('cmTemperature') || 0.2),
    characterTarget: val('cmCharacterTarget'), keyword: val('cmKeyword'), chapter: num('cmChapter'), start: num('cmStart'), end: num('cmEnd'), maxWorkers: num('cmWorkers', 4), allChapters: checked('cmAll'), concurrent: checked('cmConcurrent')
  });
  const collectPlotPayload = (scope) => ({
    source: val('cpSource'), currentPlotFile: val('cpCurrentPlotFile'), outputDir: val('cpOutputDir'), outputFile: val('cpOutputFile'), platform: val('cpPlatform') || 'deepseek', apiKey: val('cpApiKey'), baseUrl: val('cpBaseUrl'), modelName: val('cpModelName'), temperature: Number(val('cpTemperature') || 0.2),
    scope, mode: val('cpMode') || 'extract_merge', chapter: num('cpChapter'), aroundChapter: num('cpAroundChapter'), start: num('cpStart'), end: num('cpEnd'), targetWords: num('cpTargetWords', 260), recentContextCount: num('cpRecentContext', 5), maxWorkers: num('cpWorkers', 4), replaceExisting: checked('cpReplaceExisting')
  });

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
      else if (kind === 'folder') path = await callApi('choose_folder', config);
      else if (kind === 'save') path = await callApi('choose_file', config, true, 'output.txt');
      else if (kind === 'auth') path = await (api()?.choose_login_state ? callApi('choose_login_state', config) : callApi('choose_file', config, false, 'state.json'));
      else path = await callApi('choose_file', config, false, 'novel.txt');
      if (path && target) setVal(target, path);
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
        const payload = collectPublishPayload('sy', button.dataset.operation || 'publish');
        await saveConfig({ chapter_sync: payload });
        log(await callApi('chapter_sync_run', payload) ? '番茄同步任务已启动。' : '番茄同步任务未启动。', 'success');
      } else if (run === 'novel_splitter') {
        const payload = collectNovelSplitPayload();
        await saveConfig({ novel_splitter: payload });
        log(await callApi('novel_split_run', payload) ? '小说分割任务已启动。' : '小说分割任务未启动。', 'success');
      } else if (run === 'clean_text') {
        const payload = collectCleanTextPayload(button.dataset.scope || 'ad');
        await saveConfig({ clean_text: payload });
        log(await callApi('clean_text_run', payload) ? (payload.scope === 'move' ? '句子修复任务已启动。' : '广告清理任务已启动。') : '文本清理任务未启动。', 'success');
      } else if (run === 'web_crawler') {
        const payload = collectCrawlerPayload();
        await saveConfig({ web_crawler: payload });
        log(await callApi('web_crawler_run', payload) ? '网页抓取任务已启动。' : '网页抓取任务未启动。', 'success');
      } else if (run === 'web_crawler_preview') {
        const result = await callApi('web_crawler_preview', val('nsUrl'), val('nsOutput'));
        if (result.outputFile) setVal('nsOutput', result.outputFile);
        log(result.message || `预览完成：${result.title || '未知标题'}`, result.ok === false ? 'warn' : 'success');
      } else if (run === 'character_material') {
        const payload = collectCharacterPayload();
        await saveConfig({ character_material: payload });
        log(await callApi('character_material_run', payload) ? '角色素材抽取已启动。' : '角色素材抽取未启动。', 'success');
      } else if (run === 'current_plot') {
        const payload = collectPlotPayload(button.dataset.scope || 'range');
        await saveConfig({ current_plot: payload });
        log(await callApi('current_plot_run', payload) ? '当前剧情总结已启动。' : '当前剧情总结未启动。', 'success');
      } else {
        const ok = await callApi(run);
        log(ok ? '操作已提交。' : '当前没有可处理任务。', ok ? 'success' : 'warn');
      }
    } catch (error) { log(error.message, 'error'); }
  }));

  document.querySelectorAll('[data-process]').forEach((button) => button.addEventListener('click', async () => {
    try {
      const payload = collectProcessPayload(button.dataset.process, button.dataset.logTarget || 'process_novel');
      await saveConfig({ process_novel: payload });
      log(await callApi('process_novel_run', payload) ? '小说处理任务已启动。' : '小说处理任务未启动。', 'success');
    } catch (error) { log(error.message, 'error'); }
  }));

  setStyle(['pixel', 'night'].includes(localStorage.getItem('fanqieUiTheme')) ? localStorage.getItem('fanqieUiTheme') : 'pixel');
  setView('publish');
  refresh();
})();
