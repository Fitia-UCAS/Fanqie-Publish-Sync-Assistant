(function () {
  window.NovelCharacterMaterialMethods = {
    collectCharacterMaterialConfig() {
      return {
        source: document.getElementById('cmSource')?.value || '',
        outputDir: document.getElementById('cmOutputDir')?.value || '',
        characterTarget: document.getElementById('cmCharacterTarget')?.value || '',
        keyword: document.getElementById('cmKeyword')?.value || '',
        platform: document.getElementById('cmPlatform')?.value || 'deepseek',
        apiKey: document.getElementById('cmApiKey')?.value || '',
        baseUrl: document.getElementById('cmBaseUrl')?.value || '',
        modelName: document.getElementById('cmModelName')?.value || '',
        temperature: Number(document.getElementById('cmTemperature')?.value || 0.2),
        chapter: document.getElementById('cmChapter')?.value || '',
        start: document.getElementById('cmStart')?.value || '',
        end: document.getElementById('cmEnd')?.value || '',
        allChapters: !!document.getElementById('cmAll')?.checked,
        concurrent: !!document.getElementById('cmConcurrent')?.checked,
        maxWorkers: Number(document.getElementById('cmWorkers')?.value || 4),
      };
    },
    bindCharacterMaterialPage() {
      this.bindChooseFile('cmChooseSource', 'character_material.source', 'cmSource', '选择完整小说 TXT');
      this.bindChooseFolder('cmChooseOutputDir', 'character_material.outputDir', 'cmOutputDir', '自动生成 / 选择目录');
      document.getElementById('cmPlatform')?.addEventListener('change', () => this.refreshCharacterMaterialPlatformDefaults());
      document.getElementById('cmRun')?.addEventListener('click', () => this.characterMaterialRun());
      document.getElementById('cmStop')?.addEventListener('click', () => this.stopTask('character_material_stop', 'character_material'));
    },
    async refreshCharacterMaterialPlatformDefaults() {
      if (!this.api.character_material_platform_defaults) return;
      const platform = document.getElementById('cmPlatform')?.value || 'deepseek';
      const result = await this.api.character_material_platform_defaults(platform);
      if (!result || !result.ok) return;
      const base = document.getElementById('cmBaseUrl');
      const model = document.getElementById('cmModelName');
      if (base && !base.value) base.value = result.baseUrl || '';
      if (model && !model.value) model.value = result.modelName || '';
      this.debounceSavePage('character_material');
    },
    async characterMaterialRun() {
      const payload = this.collectCharacterMaterialConfig();
      this.state.config.character_material = payload;
      await this.saveConfig();
      this.beginTaskUi('character_material', '准备按章节抽取角色素材...');
      const ok = await this.api.character_material_run(payload);
      if (!ok) this.toast('任务没有启动，请查看日志。', 'warning', 'character_material');
    },
  };
})();
