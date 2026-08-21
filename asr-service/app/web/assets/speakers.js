/* 说话人管理页（声纹库）：列表 / 改名备注 / 删除 / 登记样本 / 单文件识别 / 降级指引。
 * 体例同 offline.js/stream.js：无构建 IIFE，依赖全局 Vue / naive / AsrCommon。
 * 消费 /v2/speakers* 管理 API：登记 POST（多文件 files）、识别 POST /identify（单文件 file）、
 * 列表 GET、改名 PATCH、删除 DELETE；登记与识别弹窗仅 blocked==='' 时可见。
 */
(function () {
  'use strict';
  const { ref, reactive, computed, watch, onMounted, h } = Vue;
  const { fmtDate, apiKey, authHeaders, mountApp, makeT, locale } = window.AsrCommon;

  const M = {
    zh: {
      'page.title': '说话人管理 - Qwen3-ASR Service',
      // 卡片头 / 刷新
      'card.title': '说话人库', 'btn.refresh': '刷新',
      // 表头与表内文案
      'col.name': '名称', 'col.source': '来源', 'col.templateCount': '模板数',
      'col.createdAt': '创建时间', 'col.actions': '操作',
      'source.auto': '自动登记', 'source.manual': '手动登记',
      'btn.edit': '改名/备注', 'btn.delete': '删除',
      'confirm.deletePositive': '删除', 'confirm.deleteNegative': '取消',
      'confirm.deleteBody': '硬删除不可恢复：声纹模板与留存音频将一并清除，该说话人在后续转写中退回匿名。',
      // 列表说明 / 空态
      'list.note': '数据永不自动清理；「自动登记」条目来自离线转写的声纹识别（identify_speakers），改名后立即在后续转写中生效。',
      'list.empty': '暂无说话人：开启 identify_speakers 转写多人音频可自动登记，或经 POST /v2/speakers 手动登记',
      // 编辑弹窗
      'edit.title': '改名 / 备注', 'edit.nameLabel': '显示名称',
      'edit.namePlaceholder': '如：张三', 'edit.noteLabel': '备注（可选）',
      'edit.notePlaceholder': '如：产品部，周会常驻',
      'btn.cancel': '取消', 'btn.save': '保存',
      // 消息提示
      'msg.nameRequired': '名称不能为空',
      'msg.saved': '已保存（后续转写将直接显示新名字）',
      'msg.saveFailed': '保存失败：{0}',
      'msg.deleted': '已删除：{0}（该说话人在后续转写中退回匿名）',
      'msg.deleteFailed': '删除失败：{0}',
      // 降级指引（四态 + error）
      'block.needKey.title': '需要 API Key',
      'block.needKey.body': '声纹库接口强制鉴权：请点击右上角钥匙图标配置 API Key 后刷新。',
      'block.unauthorized.title': 'API Key 无效',
      'block.unauthorized.body': '鉴权失败（401）：请核对右上角配置的 API Key 是否与服务端一致。',
      'block.disabled.title': '声纹库未启用',
      'block.disabled.body': '启用方法：服务端开启 enable_speaker 与 enable_speaker_db，且必须配置 api_key（声纹属生物识别信息，不允许无鉴权访问）。',
      'block.mismatch.title': '声纹模型版本不一致',
      'block.mismatch.body': '库内模板与当前引擎 model_tag 不一致：登记/识别已禁用，仅保留查看与删除。处理方式：删除库文件重建，或回退到登记时的引擎版本。',
      'block.error.title': '加载失败',
      // 登记弹窗
      'btn.enroll': '登记说话人', 'btn.identify': '识别说话人',
      'btn.enrollSubmit': '登记', 'btn.identifySubmit': '识别',
      'enroll.title': '登记说话人', 'enroll.nameLabel': '显示名称',
      'enroll.namePlaceholder': '如：张三', 'enroll.noteLabel': '备注（可选）',
      'enroll.notePlaceholder': '如：产品部，周会常驻',
      'enroll.consentLabel': '我已确认：样本音频已获数据主体知情同意，声纹属于生物识别信息，仅用于本服务的声纹识别。',
      'enroll.uploadHint': '点击或拖拽上传单人音频文件（可多选）',
      'enroll.formats': 'wav / mp3 / flac / m4a / aac / ogg / wma / amr / opus',
      'msg.enrollSuccess': '登记成功：{0}（{1} 条模板）',
      'msg.enrollSuccessHint': '登记成功：{0}（{1} 条模板，{2}）',
      'msg.enrollConsentRequired': '必须勾选同意声明',
      'msg.enrollNoFile': '请至少选择 1 个音频文件',
      'msg.enrollFailed': '登记失败：{0}',
      // 识别弹窗
      'identify.title': '识别说话人', 'identify.uploadHint': '上传音频文件进行 1:N 识别',
      'identify.matched': '匹配到：{0}', 'identify.unmatched': '未匹配（相似度不足）',
      'identify.score': '相似度：{0}',
      'identify.noFile': '请选择音频文件',
      'identify.failed': '识别失败：{0}',
      'identify.noMatchHint': '未匹配：声纹库中无足够相似的模板。',
      // 模板管理弹窗
      'btn.templates': '模板',
      'tmpl.title': '{0} · 模板管理',
      'tmpl.col.id': '序号', 'tmpl.col.dur': '时长', 'tmpl.col.created': '创建时间', 'tmpl.col.actions': '操作',
      'tmpl.btn.add': '追加', 'tmpl.btn.delete': '删除',
      'tmpl.addHint': '点击或拖拽上传单人音频样本，将追加到该说话人的模板',
      'tmpl.confirmDelete': '确认删除此模板？删除后质心将自动重算。',
      'tmpl.maxHint': '模板数已达上限（{0} 条）：删除部分旧模板后才能继续追加。',
      'tmpl.noTemplates': '暂无模板',
      'tmpl.deleteLastHint': '已删除最后一条模板：识别仍使用最后一次质心；建议追加样本或删除该说话人',
      'msg.tmplOpenFailed': '模板加载失败：{0}',
      'msg.tmplNoFile': '请选择音频文件',
      'msg.addTmplSuccess': '已追加 1 条模板（共 {0} 条）',
      'msg.addTmplFailed': '追加模板失败：{0}',
      'msg.delTmplSuccess': '已删除模板（剩 {0} 条）',
      'msg.delTmplFailed': '删除模板失败：{0}',
    },
    en: {
      'page.title': 'Speaker Management - Qwen3-ASR Service',
      'card.title': 'Speaker library', 'btn.refresh': 'Refresh',
      'col.name': 'Name', 'col.source': 'Source', 'col.templateCount': 'Templates',
      'col.createdAt': 'Created', 'col.actions': 'Actions',
      'source.auto': 'Auto-enrolled', 'source.manual': 'Manual',
      'btn.edit': 'Rename / Note', 'btn.delete': 'Delete',
      'confirm.deletePositive': 'Delete', 'confirm.deleteNegative': 'Cancel',
      'confirm.deleteBody': 'Hard delete is irreversible: voiceprint templates and retained audio are removed; this speaker falls back to anonymous in subsequent transcriptions.',
      'list.note': 'Data is never auto-cleaned; “Auto-enrolled” entries come from speaker identification in offline transcription (identify_speakers), and renames take effect immediately in subsequent transcriptions.',
      'list.empty': 'No speakers yet: enable identify_speakers to transcribe multi-speaker audio for auto-enrollment, or enroll manually via POST /v2/speakers',
      'edit.title': 'Rename / Note', 'edit.nameLabel': 'Display name',
      'edit.namePlaceholder': 'e.g. John', 'edit.noteLabel': 'Note (optional)',
      'edit.notePlaceholder': 'e.g. Product team, weekly regular',
      'btn.cancel': 'Cancel', 'btn.save': 'Save',
      'msg.nameRequired': 'Name cannot be empty',
      'msg.saved': 'Saved (the new name shows directly in subsequent transcriptions)',
      'msg.saveFailed': 'Save failed: {0}',
      'msg.deleted': 'Deleted: {0} (this speaker falls back to anonymous in subsequent transcriptions)',
      'msg.deleteFailed': 'Delete failed: {0}',
      'block.needKey.title': 'API Key required',
      'block.needKey.body': 'The speaker library API enforces authentication: click the key icon at the top right to configure your API Key, then refresh.',
      'block.unauthorized.title': 'Invalid API Key',
      'block.unauthorized.body': 'Authentication failed (401): verify that the API Key configured at the top right matches the server.',
      'block.disabled.title': 'Speaker library disabled',
      'block.disabled.body': 'To enable: turn on enable_speaker and enable_speaker_db on the server, and api_key must be configured (voiceprints are biometric data and may not be accessed without authentication).',
      'block.mismatch.title': 'Voiceprint model version mismatch',
      'block.mismatch.body': 'Templates in the library do not match the current engine model_tag: enrollment/identification is disabled, only view and delete remain. Fix: delete the library file and rebuild, or roll back to the engine version used at enrollment.',
      'block.error.title': 'Load failed',
      // Enroll modal
      'btn.enroll': 'Enroll Speaker', 'btn.identify': 'Identify',
      'btn.enrollSubmit': 'Enroll', 'btn.identifySubmit': 'Identify',
      'enroll.title': 'Enroll Speaker', 'enroll.nameLabel': 'Display name',
      'enroll.namePlaceholder': 'e.g. John', 'enroll.noteLabel': 'Note (optional)',
      'enroll.notePlaceholder': 'e.g. Product team, weekly regular',
      'enroll.consentLabel': 'I confirm that the audio samples have been obtained with the data subject\'s informed consent; voiceprints are biometric data and are used solely for speaker identification in this service.',
      'enroll.uploadHint': 'Click or drag to upload single-speaker audio files (multi-select)',
      'enroll.formats': 'wav / mp3 / flac / m4a / aac / ogg / wma / amr / opus',
      'msg.enrollSuccess': 'Enrolled: {0} ({1} template(s))',
      'msg.enrollSuccessHint': 'Enrolled: {0} ({1} template(s), {2})',
      'msg.enrollConsentRequired': 'Must check the consent declaration',
      'msg.enrollNoFile': 'Select at least 1 audio file',
      'msg.enrollFailed': 'Enrollment failed: {0}',
      // Identify modal
      'identify.title': 'Identify Speaker', 'identify.uploadHint': 'Upload an audio file for 1:N speaker identification',
      'identify.matched': 'Matched: {0}', 'identify.unmatched': 'Unmatched (similarity below threshold)',
      'identify.score': 'Similarity: {0}',
      'identify.noFile': 'Please select an audio file',
      'identify.failed': 'Identification failed: {0}',
      'identify.noMatchHint': 'No match: no templates in the library with sufficient similarity.',
      // Template management modal
      'btn.templates': 'Templates',
      'tmpl.title': '{0} · Templates',
      'tmpl.col.id': '#', 'tmpl.col.dur': 'Duration', 'tmpl.col.created': 'Created', 'tmpl.col.actions': 'Actions',
      'tmpl.btn.add': 'Add', 'tmpl.btn.delete': 'Delete',
      'tmpl.addHint': 'Click or drag a single-speaker audio sample to add to this speaker',
      'tmpl.confirmDelete': 'Delete this template? The centroid is recomputed automatically.',
      'tmpl.maxHint': 'Template limit reached ({0}): delete an existing one before adding more.',
      'tmpl.noTemplates': 'No templates yet',
      'tmpl.deleteLastHint': 'Last template removed: identification still uses the last centroid; add samples or delete this speaker',
      'msg.tmplOpenFailed': 'Failed to load templates: {0}',
      'msg.tmplNoFile': 'Please select an audio file',
      'msg.addTmplSuccess': '1 template added ({0} total)',
      'msg.addTmplFailed': 'Add template failed: {0}',
      'msg.delTmplSuccess': 'Template deleted ({0} remaining)',
      'msg.delTmplFailed': 'Delete template failed: {0}',
    },
  };
  const t = makeT(M);

  const AppBody = {
    setup() {
      const message = naive.useMessage();

      // —— 列表状态 ——
      const rows = reactive([]);
      const loading = ref(false);
      // 降级指引：'' 正常 | need_key | unauthorized | disabled | mismatch | error
      const blocked = ref('');
      const blockedDetail = ref('');

      async function load() {
        loading.value = true;
        blocked.value = '';
        try {
          const r = await fetch('/v2/speakers', { headers: authHeaders() });
          if (r.status === 401) {
            blocked.value = apiKey.value.trim() ? 'unauthorized' : 'need_key';
            return;
          }
          if (r.status === 503) {
            const detail = (await r.json()).detail || '';
            blocked.value = detail === 'model_tag_mismatch' ? 'mismatch' : 'disabled';
            return;
          }
          if (!r.ok) {
            blocked.value = 'error';
            blockedDetail.value = 'HTTP ' + r.status;
            return;
          }
          const data = await r.json();
          rows.length = 0;
          rows.push(...(data.speakers || []));
        } catch (e) {
          blocked.value = 'error';
          blockedDetail.value = String(e);
        } finally {
          loading.value = false;
        }
      }
      onMounted(load);

      // 四态降级指引：用函数取词以随语言切换刷新（computed 内调用即响应）
      function blockGuide(key) {
        const TYPES = {
          need_key: 'warning', unauthorized: 'error',
          disabled: 'warning', mismatch: 'error', error: 'error',
        };
        const CAMEL = {
          need_key: 'needKey', unauthorized: 'unauthorized',
          disabled: 'disabled', mismatch: 'mismatch', error: 'error',
        };
        const c = CAMEL[key];
        const body = key === 'error' ? blockedDetail.value : t('block.' + c + '.body');
        return { type: TYPES[key], title: t('block.' + c + '.title'), body };
      }
      const guide = computed(() => (blocked.value ? blockGuide(blocked.value) : null));

      // —— 编辑（改名 / 备注）——
      const edit = reactive({ show: false, id: '', name: '', note: '', saving: false });
      function openEdit(row) {
        edit.id = row.id;
        edit.name = row.name;
        edit.note = row.note || '';
        edit.show = true;
      }
      async function saveEdit() {
        if (!edit.name.trim()) { message.warning(t('msg.nameRequired')); return; }
        edit.saving = true;
        try {
          const r = await fetch('/v2/speakers/' + edit.id, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ name: edit.name.trim(), note: edit.note.trim() || null }),
          });
          if (!r.ok) throw new Error((await r.json()).detail || 'HTTP ' + r.status);
          message.success(t('msg.saved'));
          edit.show = false;
          await load();
        } catch (e) {
          message.error(t('msg.saveFailed', e.message));
        } finally {
          edit.saving = false;
        }
      }

      // —— 删除（硬删除，不可恢复）——
      async function removeSpeaker(row) {
        try {
          const r = await fetch('/v2/speakers/' + row.id, {
            method: 'DELETE', headers: authHeaders(),
          });
          if (!r.ok) throw new Error((await r.json()).detail || 'HTTP ' + r.status);
          message.success(t('msg.deleted', row.name));
          await load();
        } catch (e) {
          message.error(t('msg.deleteFailed', e.message));
        }
      }

      // —— API 错误统一处理：返回 detail 字符串；401 时更新 blocked 态并关闭弹窗 ——
      function handleError(r, onClose) {
        return (async () => {
          if (r.status === 401) {
            blocked.value = apiKey.value.trim() ? 'unauthorized' : 'need_key';
            if (onClose) onClose();
            return t('block.unauthorized.title');
          }
          const d = await r.json().catch(() => ({}));
          return (d.detail || 'HTTP ' + r.status);
        })();
      }

      // —— 登记说话人 ——
      const enroll = reactive({ show: false, name: '', note: '', consent: false, files: [], submitting: false });
      function openEnroll() {
        enroll.show = true; enroll.name = ''; enroll.note = ''; enroll.consent = false; enroll.files = [];
      }
      async function submitEnroll() {
        if (!enroll.name.trim()) { message.warning(t('msg.nameRequired')); return; }
        if (!enroll.consent) { message.warning(t('msg.enrollConsentRequired')); return; }
        if (!enroll.files.length) { message.warning(t('msg.enrollNoFile')); return; }
        enroll.submitting = true;
        const form = new FormData();
        form.append('name', enroll.name.trim());
        form.append('consent', 'true');
        if (enroll.note.trim()) form.append('note', enroll.note.trim());
        enroll.files.forEach(f => form.append('files', f.file));
        try {
          const r = await fetch('/v2/speakers', { method: 'POST', body: form, headers: authHeaders() });
          if (!r.ok) {
            const detail = await handleError(r, () => { enroll.show = false; });
            throw new Error(detail);
          }
          const data = await r.json();
          const hint = data.quality_hint ? t('msg.enrollSuccessHint', data.name, data.templates, data.quality_hint)
                                          : t('msg.enrollSuccess', data.name, data.templates);
          message.success(hint);
          enroll.show = false; enroll.files = [];
          await load();
        } catch (e) {
          message.error(t('msg.enrollFailed', e.message));
        } finally {
          enroll.submitting = false;
        }
      }

      // —— 模板管理（追加/删除模板）——
      const tmpl = reactive({
        show: false, speakerId: '', speakerName: '', templates: [], loading: false,
        addFiles: [], adding: false,
      });
      let tmplFetchSeq = 0;   // 弹窗内列表请求序号：快速开关弹窗时丢弃过期响应（防竞态覆盖）
      // —— 识别说话人（单文件 1:N）——
      const identify = reactive({ show: false, files: [], submitting: false, result: null, error: '' });
      function openIdentify() {
        identify.show = true; identify.files = []; identify.result = null; identify.error = '';
      }
      async function submitIdentify() {
        if (!identify.files.length) { message.warning(t('identify.noFile')); return; }
        identify.submitting = true; identify.result = null; identify.error = '';
        const form = new FormData();
        form.append('file', identify.files[0].file);
        try {
          const r = await fetch('/v2/speakers/identify', { method: 'POST', body: form, headers: authHeaders() });
          if (!r.ok) {
            const detail = await handleError(r, () => { identify.show = false; });
            throw new Error(detail);
          }
          identify.result = await r.json();
        } catch (e) {
          identify.error = e.message;
        } finally {
          identify.submitting = false;
        }
      }

      // —— 模板管理：打开弹窗（GET 详情含模板列表）——
      async function openTmpl(row) {
        tmpl.speakerId = row.id;
        tmpl.speakerName = row.name;
        tmpl.show = true;
        tmpl.templates = [];
        tmpl.addFiles = [];
        tmpl.adding = false;
        tmpl.loading = true;
        const seq = ++tmplFetchSeq;
        try {
          const r = await fetch('/v2/speakers/' + row.id, { headers: authHeaders() });
          if (seq !== tmplFetchSeq) return;   // 过期响应（弹窗已重开），丢弃
          if (!r.ok) {
            const detail = await handleError(r, () => { tmpl.show = false; });
            throw new Error(detail);
          }
          const data = await r.json();
          tmpl.templates = data.templates || [];
        } catch (e) {
          if (seq !== tmplFetchSeq) return;   // 过期响应：不关新弹窗、不提示旧错误
          tmpl.show = false;
          message.error(t('msg.tmplOpenFailed', e.message));
        } finally {
          if (seq === tmplFetchSeq) tmpl.loading = false;
        }
      }

      // —— 模板管理：刷新弹窗内列表（不关弹窗）——
      async function reloadTmpl() {
        if (!tmpl.speakerId) return;
        const seq = ++tmplFetchSeq;
        try {
          const r = await fetch('/v2/speakers/' + tmpl.speakerId, { headers: authHeaders() });
          if (seq !== tmplFetchSeq) return;
          if (!r.ok) {
            const detail = await handleError(r, () => { tmpl.show = false; });
            throw new Error(detail);
          }
          const data = await r.json();
          tmpl.templates = data.templates || [];
        } catch (e) {
          if (seq !== tmplFetchSeq) return;
          message.error(t('msg.tmplOpenFailed', e.message));
        }
      }

      // —— 模板管理：追加模板（单文件）——
      async function addTemplate() {
        if (!tmpl.addFiles.length) { message.warning(t('msg.tmplNoFile')); return; }
        tmpl.adding = true;
        const form = new FormData();
        form.append('file', tmpl.addFiles[0].file);
        try {
          const r = await fetch('/v2/speakers/' + tmpl.speakerId + '/templates', {
            method: 'POST', body: form, headers: authHeaders(),
          });
          if (!r.ok) {
            const detail = await handleError(r);
            throw new Error(detail);
          }
          const data = await r.json();
          tmpl.addFiles = [];
          message.success(t('msg.addTmplSuccess', data.templates));
          await reloadTmpl();
        } catch (e) {
          message.error(t('msg.addTmplFailed', e.message));
        } finally {
          tmpl.adding = false;
        }
      }

      // —— 模板管理：删除单条模板 ——
      async function confirmDeleteTmpl(trow) {
        try {
          const r = await fetch('/v2/speakers/' + tmpl.speakerId + '/templates/' + trow.id, {
            method: 'DELETE', headers: authHeaders(),
          });
          if (!r.ok) {
            const detail = await handleError(r);
            throw new Error(detail);
          }
          const data = await r.json();
          if (data.remaining === 0 && data.hint) {
            message.warning(t('tmpl.deleteLastHint'));
          } else {
            message.success(t('msg.delTmplSuccess', data.remaining));
          }
          await reloadTmpl();
        } catch (e) {
          message.error(t('msg.delTmplFailed', e.message));
        }
      }

      // —— 模板管理：关闭（Cancel 按钮路径）——按钮直接赋值不触发 update:show，需显式刷新
      function closeTmpl() {
        if (!tmpl.show) return;
        tmpl.show = false;
        load();
      }

      // —— 弹窗关闭后刷新外部列表（template_count 同步）——
      function onTmplClose() {
        if (tmpl.show) return;
        load();
      }

      // —— 模板管理弹窗表格列 ——
      // computed：t()/locale 切换刷新表头与表内文案；wide 随语言控制列宽（定义见下）
      const wide = computed(() => locale.value === 'en');
      const tmplColumns = computed(() => [
        { title: t('tmpl.col.id'), key: 'id', width: 64, align: 'center' },
        {
          title: t('tmpl.col.dur'), key: 'dur_sec', width: wide.value ? 110 : 90,
          render: row => (row.dur_sec != null ? row.dur_sec.toFixed(1) + 's' : '—'),
        },
        {
          title: t('tmpl.col.created'), key: 'created_at', width: 170,
          render: row => fmtDate(row.created_at),
        },
        {
          title: t('tmpl.col.actions'), key: 'actions', width: wide.value ? 120 : 100, align: 'right',
          render: row => h(naive.NPopconfirm, {
            onPositiveClick: () => confirmDeleteTmpl(row),
            positiveText: t('confirm.deletePositive'), negativeText: t('confirm.deleteNegative'),
            positiveButtonProps: { type: 'error' },
          }, {
            trigger: () => h(naive.NButton, { size: 'tiny', tertiary: true, type: 'error' },
              { default: () => t('tmpl.btn.delete') }),
            default: () => t('tmpl.confirmDelete'),
          }),
        },
      ]);

      // —— 表格列（render 函数式，Naive UI data-table 体例）——
      // t() 随语言切换刷新表头与表内文案（wide 声明在 tmplColumns 前）
      const columns = computed(() => [
        {
          title: t('col.name'), key: 'name',
          render: row => h('div', null, [
            h('span', { style: 'font-weight:600;' }, row.name),
            row.note ? h('div', { style: 'font-size:.78em;opacity:.65;' }, row.note) : null,
          ]),
        },
        {
          title: t('col.source'), key: 'source', width: wide.value ? 132 : 96,
          render: row => h(naive.NTag, {
            size: 'small', bordered: false,
            type: row.source === 'auto' ? 'warning' : 'success',
          }, { default: () => (row.source === 'auto' ? t('source.auto') : t('source.manual')) }),
        },
        { title: t('col.templateCount'), key: 'template_count', width: wide.value ? 110 : 80, align: 'center' },
        {
          title: t('col.createdAt'), key: 'created_at', width: 170,
          render: row => fmtDate(row.created_at),
        },
        {
          title: t('col.actions'), key: 'actions', width: wide.value ? 270 : 200, align: 'right',
          render: row => h(naive.NSpace, { justify: 'end', size: 'small' }, {
            default: () => [
              h(naive.NButton, { size: 'tiny', tertiary: true, onClick: () => openTmpl(row) },
                { default: () => t('btn.templates') }),
              h(naive.NButton, { size: 'tiny', tertiary: true, onClick: () => openEdit(row) },
                { default: () => t('btn.edit') }),
              h(naive.NPopconfirm, {
                onPositiveClick: () => removeSpeaker(row),
                positiveText: t('confirm.deletePositive'), negativeText: t('confirm.deleteNegative'),
                positiveButtonProps: { type: 'error' },
              }, {
                trigger: () => h(naive.NButton, { size: 'tiny', tertiary: true, type: 'error' },
                  { default: () => t('btn.delete') }),
                default: () => t('confirm.deleteBody'),
              }),
            ],
          }),
        },
      ]);

      // 页面标题本地化
      const setTitle = () => { document.title = t('page.title'); };
      setTitle();
      watch(locale, setTitle);

      return { rows, loading, guide, columns, load, edit, saveEdit, removeSpeaker,
               enroll, openEnroll, submitEnroll, identify, openIdentify, submitIdentify,
               tmpl, openTmpl, addTemplate, confirmDeleteTmpl, closeTmpl, onTmplClose, tmplColumns, t };
    },
    template: `
      <div style="max-width:980px;margin:0 auto;">
        <n-card :bordered="false" class="panel" size="small">
          <template #header>
            <span class="panel-title"><a-icon name="list" size="15"></a-icon>{{ t('card.title') }}</span>
          </template>
          <template #header-extra>
            <n-space size="small">
              <n-button v-if="!guide" size="small" tertiary :disabled="enroll.submitting" @click="openEnroll">
                <a-icon name="upload" size="14" style="margin-right:5px;"></a-icon>{{ t('btn.enroll') }}
              </n-button>
              <n-button v-if="!guide" size="small" tertiary :disabled="identify.submitting" @click="openIdentify">
                <a-icon name="mic" size="14" style="margin-right:5px;"></a-icon>{{ t('btn.identify') }}
              </n-button>
              <n-button size="small" tertiary :loading="loading" @click="load">
                <a-icon name="refresh" size="14" style="margin-right:5px;"></a-icon>{{ t('btn.refresh') }}
              </n-button>
            </n-space>
          </template>

          <n-alert v-if="guide" :type="guide.type" :title="guide.title" :show-icon="true"
                   style="margin-bottom:14px;">{{ guide.body }}</n-alert>

          <template v-if="!guide">
            <n-text depth="3" style="display:block;font-size:.8em;margin-bottom:12px;">
              {{ t('list.note') }}
            </n-text>
            <n-data-table :columns="columns" :data="rows" :loading="loading"
                          :bordered="false" size="small"
                          :row-key="row => row.id">
              <template #empty>
                <n-empty :description="t('list.empty')" size="small"></n-empty>
              </template>
            </n-data-table>
          </template>
        </n-card>

        <n-modal v-model:show="edit.show" preset="card" :title="t('edit.title')"
                 style="width:380px;" :mask-closable="!edit.saving">
          <n-space vertical size="large">
            <div>
              <n-text depth="3" style="display:block;font-size:.78em;margin-bottom:5px;">{{ t('edit.nameLabel') }}</n-text>
              <n-input v-model:value="edit.name" :placeholder="t('edit.namePlaceholder')" maxlength="64"></n-input>
            </div>
            <div>
              <n-text depth="3" style="display:block;font-size:.78em;margin-bottom:5px;">{{ t('edit.noteLabel') }}</n-text>
              <n-input v-model:value="edit.note" :placeholder="t('edit.notePlaceholder')" maxlength="200"></n-input>
            </div>
            <n-space justify="end">
              <n-button size="small" :disabled="edit.saving" @click="edit.show = false">{{ t('btn.cancel') }}</n-button>
              <n-button size="small" type="primary" :loading="edit.saving" @click="saveEdit">{{ t('btn.save') }}</n-button>
            </n-space>
          </n-space>
        </n-modal>

        <n-modal v-model:show="enroll.show" preset="card" :title="t('enroll.title')"
                 style="width:520px;" :mask-closable="!enroll.submitting">
          <n-space vertical size="large">
            <div>
              <n-text depth="3" style="display:block;font-size:.78em;margin-bottom:5px;">{{ t('enroll.nameLabel') }}</n-text>
              <n-input v-model:value="enroll.name" :placeholder="t('enroll.namePlaceholder')" maxlength="64"></n-input>
            </div>
            <div>
              <n-text depth="3" style="display:block;font-size:.78em;margin-bottom:5px;">{{ t('enroll.noteLabel') }}</n-text>
              <n-input v-model:value="enroll.note" :placeholder="t('enroll.notePlaceholder')" maxlength="200"></n-input>
            </div>
            <n-checkbox v-model:checked="enroll.consent" size="small">
              <span style="font-size:.82em;opacity:.85;">{{ t('enroll.consentLabel') }}</span>
            </n-checkbox>
            <n-upload multiple :default-upload="false" :show-file-list="true"
                      accept=".wav,.mp3,.flac,.m4a,.aac,.ogg,.wma,.amr,.opus"
                      :file-list="enroll.files" @change="(p) => { enroll.files = p.fileList || [] }">
              <n-upload-dragger>
                <div style="color:#14b8a6;margin-bottom:8px;"><a-icon name="upload" size="30"></a-icon></div>
                <n-text style="font-size:.92em;font-weight:600;">{{ t('enroll.uploadHint') }}</n-text>
                <n-p depth="3" style="font-size:.76em;margin:6px 0 0;">{{ t('enroll.formats') }}</n-p>
              </n-upload-dragger>
            </n-upload>
            <n-space justify="end">
              <n-button size="small" :disabled="enroll.submitting" @click="enroll.show = false">{{ t('btn.cancel') }}</n-button>
              <n-button size="small" type="primary" :loading="enroll.submitting" @click="submitEnroll">{{ t('btn.enrollSubmit') }}</n-button>
            </n-space>
          </n-space>
        </n-modal>

        <n-modal v-model:show="identify.show" preset="card" :title="t('identify.title')"
                 style="width:460px;" :mask-closable="!identify.submitting">
          <n-space vertical size="large">
            <n-upload :default-upload="false" :show-file-list="true"
                      accept=".wav,.mp3,.flac,.m4a,.aac,.ogg,.wma,.amr,.opus"
                      :file-list="identify.files" @change="(p) => { const list = p.fileList || []; identify.files = list.length ? [list[list.length - 1]] : [] }">
              <n-upload-dragger>
                <div style="color:#14b8a6;margin-bottom:8px;"><a-icon name="mic" size="30"></a-icon></div>
                <n-text style="font-size:.92em;font-weight:600;">{{ t('identify.uploadHint') }}</n-text>
                <n-p depth="3" style="font-size:.76em;margin:6px 0 0;">{{ t('enroll.formats') }}</n-p>
              </n-upload-dragger>
            </n-upload>
            <n-divider style="margin:0;"></n-divider>
            <template v-if="identify.result || identify.error">
              <n-alert v-if="identify.result" :title="identify.result.matched
                                ? t('identify.matched', identify.result.name || '—')
                                : t('identify.unmatched')"
                       :type="identify.result.matched ? 'success' : 'warning'" :show-icon="false">
                <template #default>
                  {{ t('identify.score', (identify.result.score != null ? identify.result.score.toFixed(3) : '—')) }}
                  <n-text v-if="!identify.result.matched" depth="3" style="font-size:.82em;margin-top:8px;display:block;">{{ t('identify.noMatchHint') }}</n-text>
                </template>
              </n-alert>
              <n-alert v-else :title="t('identify.failed', identify.error)" type="error" :show-icon="false" />
            </template>
            <n-space justify="end" v-if="!identify.result && !identify.error">
              <n-button size="small" :disabled="identify.submitting || !identify.files.length" @click="identify.show = false">{{ t('btn.cancel') }}</n-button>
              <n-button size="small" type="primary" :loading="identify.submitting" @click="submitIdentify">{{ t('btn.identifySubmit') }}</n-button>
            </n-space>
          </n-space>
        </n-modal>

        <n-modal v-model:show="tmpl.show" preset="card"
                 :title="t('tmpl.title', tmpl.speakerName || '')"
                 style="width:560px;" :mask-closable="!tmpl.loading && !tmpl.adding"
                 @update:show="onTmplClose">
          <n-space vertical size="large">
            <template v-if="tmpl.loading">
              <div style="padding:20px;text-align:center;"><n-spin size="small"></n-spin></div>
            </template>
            <template v-else>
              <!-- 模板列表 -->
              <template v-if="tmpl.templates.length">
                <n-alert v-if="tmpl.templates.length >= 16" type="warning" :show-icon="false"
                         style="margin-bottom:6px;">
                  {{ t('tmpl.maxHint', tmpl.templates.length) }}
                </n-alert>
                <n-data-table :columns="tmplColumns" :data="tmpl.templates"
                              :bordered="false" size="small" :row-key="r => r.id">
                </n-data-table>
              </template>
              <n-empty v-else :description="t('tmpl.noTemplates')" size="small"></n-empty>
              <!-- 追加区域 -->
              <n-divider style="margin:0;"></n-divider>
              <n-text depth="3" style="display:block;font-size:.78em;margin-bottom:6px;">
                {{ t('tmpl.btn.add') }}（{{ t('enroll.formats') }}）
              </n-text>
              <n-upload :default-upload="false" :show-file-list="true"
                        accept=".wav,.mp3,.flac,.m4a,.aac,.ogg,.wma,.amr,.opus"
                        :file-list="tmpl.addFiles"
                        :disabled="tmpl.adding || tmpl.templates.length >= 16"
                        @change="(p) => { const list = p.fileList || []; tmpl.addFiles = list.length ? [list[list.length - 1]] : [] }">
                <n-upload-dragger>
                  <div style="color:#14b8a6;margin-bottom:6px;"><a-icon name="upload" size="20"></a-icon></div>
                  <n-text style="font-size:.82em;font-weight:600;">{{ t('tmpl.addHint') }}</n-text>
                </n-upload-dragger>
              </n-upload>
              <div style="display:flex;justify-content:flex-end;">
                <n-button size="small" type="primary" :loading="tmpl.adding"
                          :disabled="tmpl.adding || !tmpl.addFiles.length || tmpl.templates.length >= 16"
                          @click="addTemplate">{{ t('tmpl.btn.add') }}</n-button>
              </div>
            </template>
            <n-space justify="end">
              <n-button size="small" :disabled="tmpl.adding" @click="closeTmpl">{{ t('btn.cancel') }}</n-button>
            </n-space>
          </n-space>
        </n-modal>
      </div>`,
  };

  mountApp(AppBody);
})();
