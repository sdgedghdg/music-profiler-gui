"""Simple i18n module for MusicProfiler with no external dependencies."""

from __future__ import annotations
from enum import Enum


class Lang(Enum):
    EN = "en"
    ZH = "zh"


_lang = Lang.ZH  # default to Chinese


def set_lang(lang: Lang) -> None:
    global _lang
    _lang = lang


def get_lang() -> Lang:
    return _lang


def t(key: str) -> str:
    """Return the localized string for key in the current language."""
    return STRINGS.get(key, {}).get(_lang.value, key)


# All user-visible strings in one dictionary:
STRINGS: dict[str, dict[str, str]] = {
    # -- App & window --
    "app.title": {"en": "MusicProfiler", "zh": "音乐素材管家"},
    "app.settings": {"en": "Settings", "zh": "设置"},
    "app.configure_tools": {"en": "Configure Tools", "zh": "配置工具"},

    # -- Tab names --
    "tab.library": {"en": "Library", "zh": "素材库"},
    "tab.process": {"en": "Process", "zh": "音频处理"},
    "tab.demucs": {"en": "Demucs", "zh": "去伴奏"},
    "tab.playlists": {"en": "Playlists", "zh": "歌单管理"},
    "tab.export": {"en": "Export", "zh": "导出"},

    # -- Setup Wizard --
    "wizard.title": {"en": "MusicProfiler Setup", "zh": "初始配置"},
    "wizard.header": {
        "en": "Welcome to MusicProfiler!\nPlease configure the required external tools below.",
        "zh": "欢迎使用音乐素材管家！\n请配置以下外部工具路径。",
    },
    "wizard.ffmpeg": {"en": "FFmpeg", "zh": "FFmpeg"},
    "wizard.ffprobe": {"en": "FFprobe", "zh": "FFprobe"},
    "wizard.demucs": {"en": "Demucs", "zh": "Demucs"},
    "wizard.browse": {"en": "Browse", "zh": "浏览"},
    "wizard.skip": {"en": "Skip", "zh": "跳过"},
    "wizard.finish": {"en": "Finish", "zh": "完成"},
    "wizard.missing_title": {"en": "Missing Required Tools", "zh": "缺少必要工具"},
    "wizard.missing_msg": {
        "en": "{tools} could not be validated.\n\nThese tools are required for most operations. You can continue and configure them later in Settings.\n\nContinue anyway?",
        "zh": "无法验证 {tools}。\n\n这些工具对大部分功能是必需的。你可以先继续，之后在设置中配置。\n\n是否继续？",
    },

    # -- Library Panel --
    "library.import": {"en": "Import Files", "zh": "导入文件"},
    "library.import_separated": {"en": "Import Separated", "zh": "导入分离音轨"},
    "library.import_separated_title": {"en": "Select Demucs output folder", "zh": "选择 Demucs 输出目录"},
    "library.import_separated_error": {"en": "Import Separated Tracks Error", "zh": "导入分离音轨失败"},
    "library.import_separated_result": {
        "en": "Matched {matched} songs, imported {imported} tracks, skipped {skipped}",
        "zh": "匹配 {matched} 首歌曲，导入 {imported} 条音轨，跳过 {skipped} 条",
    },
    "library.play_track": {"en": "Play Track", "zh": "播放音轨"},
    "library.play_track_entry": {"en": "{track_type}", "zh": "{track_type}"},
    "library.file_path": {"en": "File Path", "zh": "文件路径"},
    "library.search": {"en": "Search", "zh": "搜索"},
    "library.format": {"en": "Format:", "zh": "格式："},
    "library.all": {"en": "All", "zh": "全部"},
    "library.refresh": {"en": "Refresh", "zh": "刷新"},
    "library.title": {"en": "Title", "zh": "标题"},
    "library.artist": {"en": "Artist", "zh": "歌手"},
    "library.album": {"en": "Album", "zh": "专辑"},
    "library.duration": {"en": "Duration", "zh": "时长"},
    "library.format_col": {"en": "Format", "zh": "格式"},
    "library.vocal_removed": {"en": "Vocal Removed", "zh": "已去伴奏"},
    "library.tags": {"en": "Tags", "zh": "标签"},
    "library.ready": {"en": "Ready", "zh": "就绪"},
    "library.showing": {"en": "Showing {shown} of {total} songs", "zh": "显示 {shown} / {total} 首歌曲"},
    "library.showing_filtered": {
        "en": "Showing {shown} of {total} songs (filtered)",
        "zh": "显示 {shown} / {total} 首歌曲（已筛选）",
    },
    "library.imported": {"en": "Imported {n} songs ({skipped} skipped)", "zh": "已导入 {n} 首歌曲（跳过 {skipped} 首）"},
    "library.import_title": {"en": "Select audio files to import", "zh": "选择要导入的音频文件"},
    "library.import_supported": {"en": "Supported audio and NCM files", "zh": "支持的音频和 NCM 文件"},
    "library.import_error": {"en": "Import Error", "zh": "导入错误"},
    "library.delete": {"en": "Delete", "zh": "删除"},
    "library.add_tag": {"en": "Add Tag...", "zh": "添加标签..."},
    "library.confirm_delete": {"en": "Confirm Delete", "zh": "确认删除"},
    "library.delete_msg": {
        "en": "Delete \"{title}\" by {artist}?\n\nThis cannot be undone.",
        "zh": "确定要删除「{title}」- {artist} 吗？\n\n此操作不可撤销。",
    },
    "library.delete_error": {"en": "Delete Error", "zh": "删除失败"},
    "library.deleted": {"en": "Deleted \"{title}\"", "zh": "已删除「{title}」"},
    "library.tag_prompt": {"en": "Add Tag", "zh": "添加标签"},
    "library.tag_name": {"en": "Tag name:", "zh": "标签名称："},
    "library.tag_error": {"en": "Tag Error", "zh": "标签错误"},
    "library.tag_added": {"en": "Added tag \"{name}\"", "zh": "已添加标签「{name}」"},
    "library.song_detail": {"en": "Song Detail — {title}", "zh": "歌曲详情 — {title}"},
    "library.default_playlist": {
        "en": "Default: {name} · {duration}",
        "zh": "默认歌单：{name} · 总时长 {duration}",
    },
    "library.no_default_playlist": {
        "en": "No default playlist", "zh": "未设置默认歌单",
    },
    "library.add_original_to_default": {
        "en": "Add Original to Default Playlist", "zh": "添加原曲到默认歌单",
    },
    "library.add_instrumental_to_default": {
        "en": "Add Instrumental to Default Playlist", "zh": "添加伴奏到默认歌单",
    },

    # -- Process Panel --
    "process.song_selection": {"en": "Song Selection", "zh": "歌曲选择"},
    "process.transcode_settings": {"en": "Transcode Settings", "zh": "转码设置"},
    "process.output_format": {"en": "Output Format:", "zh": "输出格式："},
    "process.bitrate": {"en": "Bitrate:", "zh": "码率："},
    "process.sample_rate": {"en": "Sample Rate:", "zh": "采样率："},
    "process.channels": {"en": "Channels:", "zh": "声道："},
    "process.mono": {"en": "Mono (1)", "zh": "单声道 (1)"},
    "process.stereo": {"en": "Stereo (2)", "zh": "立体声 (2)"},
    "process.loudness_title": {"en": "Loudness Normalization", "zh": "响度标准化"},
    "process.normalize": {"en": "Normalize loudness (EBU R128)", "zh": "响度标准化 (EBU R128)"},
    "process.target_lufs": {"en": "Target LUFS:", "zh": "目标 LUFS："},
    "process.loudnorm_note": {"en": "Two-pass loudnorm will be applied", "zh": "将应用两遍 loudnorm 处理"},
    "process.transcode_btn": {"en": "Transcode Selected", "zh": "转码选中歌曲"},
    "process.normalize_btn": {"en": "Normalize Loudness", "zh": "响度标准化"},
    "process.no_selection": {"en": "No Songs Selected", "zh": "未选择歌曲"},
    "process.no_selection_msg": {
        "en": "Please select at least one song to transcode.",
        "zh": "请至少选择一首歌曲进行转码。",
    },
    "process.task_error": {"en": "Task Error", "zh": "任务错误"},
    "process.task_created": {"en": "Task Created", "zh": "任务已创建"},
    "process.task_created_msg": {
        "en": "Transcode task created (ID: {id}).\nCheck the task monitor for progress.",
        "zh": "转码任务已创建 (ID: {id})。\n请在任务监视器中查看进度。",
    },
    "process.norm_created_msg": {
        "en": "Loudness normalization task created (ID: {id}).\nCheck the task monitor for progress.",
        "zh": "响度标准化任务已创建 (ID: {id})。\n请在任务监视器中查看进度。",
    },
    "process.search_error": {"en": "Search Error", "zh": "搜索错误"},

    # -- Demucs Panel --
    "demucs.search": {"en": "Search:", "zh": "搜索："},
    "demucs.search_btn": {"en": "Search", "zh": "搜索"},
    "demucs.select_all": {"en": "Select All", "zh": "全选"},
    "demucs.deselect_all": {"en": "Deselect All", "zh": "取消全选"},
    "demucs.hide_processed": {"en": "Hide already processed", "zh": "隐藏已处理"},
    "demucs.refresh": {"en": "Refresh", "zh": "刷新"},
    "demucs.model_title": {"en": "Demucs Model", "zh": "Demucs 模型"},
    "demucs.model_note": {
        "en": "htdemucs is recommended for most music. Processing takes 2-5 minutes per song.",
        "zh": "推荐使用 htdemucs。每首歌处理约需 2-5 分钟。",
    },
    "demucs.separate_btn": {"en": "Separate Vocals", "zh": "分离人声"},
    "demucs.results_title": {"en": "Results", "zh": "处理结果"},
    "demucs.results_song": {"en": "Song", "zh": "歌曲"},
    "demucs.results_status": {"en": "Status", "zh": "状态"},
    "demucs.open_output": {"en": "Open Output Folder", "zh": "打开输出目录"},
    "demucs.task_created": {
        "en": "Task #{id} created. Check task monitor for progress.",
        "zh": "任务 #{id} 已创建，请在任务监视器中查看进度。",
    },
    "demucs.no_selection": {"en": "No Songs Selected", "zh": "未选择歌曲"},
    "demucs.no_selection_msg": {"en": "Please select at least one song.", "zh": "请至少选择一首歌曲。"},
    "demucs.unavailable": {"en": "Demucs Unavailable", "zh": "Demucs 不可用"},
    "demucs.unavailable_msg": {
        "en": "Demucs is not configured. Please set the Demucs path in Settings.",
        "zh": "Demucs 未配置，请在设置中配置 Demucs 路径。",
    },
    "demucs.vocal_path": {"en": "Vocal path", "zh": "人声路径"},
    "demucs.inst_path": {"en": "Instrumental path", "zh": "伴奏路径"},
    "demucs.play_vocal": {"en": "Play Vocal", "zh": "播放人声"},
    "demucs.play_inst": {"en": "Play Instrumental", "zh": "播放伴奏"},
    "demucs.not_configured": {"en": "Not configured", "zh": "未配置"},

    # -- Playlist Panel --
    "playlist.set_default": {"en": "Set Default", "zh": "设为默认歌单"},
    "playlist.default_marker": {"en": "★", "zh": "★"},
    "playlist.new": {"en": "New", "zh": "新建"},
    "playlist.delete": {"en": "Delete", "zh": "删除"},
    "playlist.rename": {"en": "Rename", "zh": "重命名"},
    "playlist.no_playlist": {"en": "No playlist selected", "zh": "未选择歌单"},
    "playlist.move_up": {"en": "Move Up", "zh": "上移"},
    "playlist.move_down": {"en": "Move Down", "zh": "下移"},
    "playlist.remove": {"en": "Remove", "zh": "移除"},
    "playlist.find": {"en": "Find", "zh": "查找"},
    "playlist.add_selected": {"en": "Add Selected to Playlist", "zh": "添加到歌单"},
    "playlist.add_instrumental": {"en": "Add Instrumental", "zh": "添加选中伴奏"},
    "playlist.no_instrumental": {
        "en": "{count} selected song(s) have no imported instrumental track.",
        "zh": "{count} 首选中歌曲没有已导入的伴奏音轨。",
    },
    "playlist.reference": {"en": "Reference:", "zh": "参考时长："},
    "playlist.min": {"en": "min", "zh": "分钟"},
    "playlist.remove_from": {"en": "Remove from playlist", "zh": "从歌单中移除"},
    "playlist.new_prompt": {"en": "New Playlist", "zh": "新建歌单"},
    "playlist.new_name": {"en": "Playlist name:", "zh": "歌单名称："},
    "playlist.rename_prompt": {"en": "Rename Playlist", "zh": "重命名歌单"},
    "playlist.rename_name": {"en": "New name:", "zh": "新名称："},
    "playlist.confirm_delete": {"en": "Delete Playlist", "zh": "删除歌单"},
    "playlist.confirm_delete_msg": {
        "en": "Delete playlist \"{name}\"?\n\nThis cannot be undone.",
        "zh": "确定要删除歌单「{name}」吗？\n\n此操作不可撤销。",
    },
    "playlist.error": {"en": "Error", "zh": "错误"},
    "playlist.error_load": {"en": "Could not load playlists.", "zh": "无法加载歌单。"},
    "playlist.error_load_songs": {"en": "Could not load playlist.", "zh": "无法加载歌单内容。"},
    "playlist.stats": {
        "en": "{name} — {count} songs | {total} total | {remaining} remaining ({ref} min reference)",
        "zh": "{name} — {count} 首 | 总时长 {total} | 距 {ref} 分钟还差 {remaining}",
    },
    "playlist.search": {"en": "Search:", "zh": "搜索："},

    # -- Playlist Table Export --
    "playlist.export_table": {"en": "Export Table", "zh": "导出歌单表"},
    "playlist.export_table_title": {"en": "Export Playlist Table", "zh": "导出歌单表"},
    "playlist.export_table_csv_type": {
        "en": "CSV table (Excel)", "zh": "CSV 表格（Excel）",
    },
    "playlist.export_table_md_type": {
        "en": "Markdown table", "zh": "Markdown 表格",
    },
    "playlist.export_table_no_selection": {
        "en": "No Playlist Selected", "zh": "未选择歌单",
    },
    "playlist.export_table_no_selection_msg": {
        "en": "Please select a playlist first.", "zh": "请先选择一个歌单。",
    },
    "playlist.export_table_done": {"en": "Export Complete", "zh": "导出完成"},
    "playlist.export_table_done_msg": {
        "en": "Playlist table saved to:\n{path}",
        "zh": "歌单表已保存到：\n{path}",
    },
    "playlist.export_table_error": {"en": "Export Failed", "zh": "导出失败"},
    "playlist.export_table_error_msg": {
        "en": "Could not export the playlist table:\n{error}",
        "zh": "无法导出歌单表：\n{error}",
    },
    "table.index": {"en": "#", "zh": "序号"},
    "table.title": {"en": "Title", "zh": "曲名"},
    "table.artist": {"en": "Artist", "zh": "歌手"},
    "table.album": {"en": "Album", "zh": "专辑"},
    "table.variant": {"en": "Version", "zh": "版本"},
    "table.duration": {"en": "Duration", "zh": "时长"},
    "table.cumulative": {"en": "Cumulative", "zh": "累计时长"},
    "table.total": {"en": "Total", "zh": "合计"},
    "table.song_count": {"en": "{count} songs", "zh": "{count} 首"},
    "table.total_duration": {
        "en": "Total duration: {duration}", "zh": "总时长：{duration}",
    },
    "table.doc_title": {"en": "Playlist — {name}", "zh": "歌单 — {name}"},
    "table.description": {
        "en": "Description: {description}", "zh": "说明：{description}",
    },
    "table.variant_original": {"en": "Original", "zh": "原曲"},
    "table.variant_instrumental": {"en": "Instrumental", "zh": "伴奏"},
    "table.variant_vocals": {"en": "Vocals", "zh": "人声"},
    "table.variant_drums": {"en": "Drums", "zh": "鼓"},
    "table.variant_bass": {"en": "Bass", "zh": "贝斯"},
    "table.variant_other": {"en": "Other", "zh": "其他"},

    # -- Export Panel --
    "export.playlist": {"en": "Playlist", "zh": "歌单"},
    "export.select_playlist": {"en": "Select a playlist...", "zh": "请选择歌单..."},
    "export.validate": {"en": "Validate", "zh": "验证"},
    "export.settings": {"en": "Export Settings", "zh": "导出设置"},
    "export.output_format": {"en": "Output format:", "zh": "输出格式："},
    "export.bitrate": {"en": "Bitrate (kbps):", "zh": "码率 (kbps)："},
    "export.sample_rate": {"en": "Sample rate (Hz):", "zh": "采样率 (Hz)："},
    "export.normalize": {"en": "Normalize loudness (EBU R128)", "zh": "响度标准化 (EBU R128)"},
    "export.coming_soon": {"en": "Coming soon", "zh": "即将推出"},
    "export.crossfade": {"en": "Crossfade:", "zh": "交叉淡入淡出："},
    "export.fade_in": {"en": "Fade in:", "zh": "淡入："},
    "export.fade_out": {"en": "Fade out:", "zh": "淡出："},
    "export.reference_title": {"en": "Reference Duration", "zh": "参考时长"},
    "export.reference": {"en": "Reference duration (minutes):", "zh": "参考时长（分钟）："},
    "export.under": {"en": "under", "zh": "少于"},
    "export.over": {"en": "over", "zh": "超出"},
    "export.remaining": {
        "en": "Your playlist is {time} {direction} the reference",
        "zh": "当前歌单{direction}参考时长 {time}",
    },
    "export.export_btn": {"en": "Export Broadcast File", "zh": "导出广播文件"},
    "export.history": {"en": "Export History", "zh": "导出历史"},
    "export.recent": {"en": "Recent exports will appear here.", "zh": "最近的导出记录将显示在这里。"},
    "export.open_output": {"en": "Open Export Folder", "zh": "打开导出目录"},
    "export.no_playlist": {"en": "Export Validation", "zh": "导出验证"},
    "export.no_playlist_msg": {"en": "Please select a playlist first.", "zh": "请先选择一个歌单。"},
    "export.validation_ok": {"en": "Export Validation", "zh": "导出验证"},
    "export.validation_ok_msg": {"en": "All files are present and valid.", "zh": "所有文件完整有效。"},
    "export.validation_warn": {"en": "Export Validation", "zh": "导出验证"},
    "export.task_created": {"en": "Export Task", "zh": "导出任务"},
    "export.task_created_msg": {
        "en": "Export task created (ID: {id}).\nCheck the task monitor for progress.",
        "zh": "导出任务已创建 (ID: {id})。\n请在任务监视器中查看进度。",
    },
    "export.error": {"en": "Export Error", "zh": "导出错误"},

    # -- Task Monitor --
    "tasks.collapsed": {
        "en": "Tasks: {pending} pending | {running} running | {done} completed",
        "zh": "任务：{pending} 等待 | {running} 进行中 | {done} 已完成",
    },
    "tasks.processing": {"en": "Processing {type} ({pct}%)", "zh": "正在处理 {type} ({pct}%)"},
    "tasks.show": {"en": "Show Tasks", "zh": "显示任务"},
    "tasks.hide": {"en": "Hide", "zh": "隐藏"},
    "tasks.id": {"en": "ID", "zh": "编号"},
    "tasks.type": {"en": "Type", "zh": "类型"},
    "tasks.status": {"en": "Status", "zh": "状态"},
    "tasks.progress": {"en": "Progress", "zh": "进度"},
    "tasks.created": {"en": "Created", "zh": "创建时间"},
    "tasks.clear": {"en": "Clear Completed", "zh": "清除已完成"},
    "tasks.cancel": {"en": "Cancel", "zh": "取消"},
    "tasks.type_transcode": {"en": "transcode", "zh": "转码"},
    "tasks.type_demucs": {"en": "demucs", "zh": "去伴奏"},
    "tasks.type_export": {"en": "export", "zh": "导出"},
    "tasks.type_import": {"en": "import", "zh": "导入"},
    "tasks.type_decrypt": {"en": "decrypt", "zh": "解密"},

    # -- Services / error messages shown to user --
    "error.song_not_found": {"en": "Song not found", "zh": "歌曲未找到"},
    "error.playlist_not_found": {"en": "Playlist not found", "zh": "歌单未找到"},
    "error.empty_playlist": {"en": "Playlist has no songs to export", "zh": "歌单中没有歌曲可供导出"},
    "error.file_not_found": {"en": "File not found", "zh": "文件未找到"},
    "error.import_failed": {"en": "Import failed", "zh": "导入失败"},

    # -- Song detail dialog --
    "detail.title": {"en": "Title", "zh": "标题"},
    "detail.artist": {"en": "Artist", "zh": "歌手"},
    "detail.album": {"en": "Album", "zh": "专辑"},
    "detail.path": {"en": "Path", "zh": "路径"},
    "detail.duration": {"en": "Duration", "zh": "时长"},
    "detail.format": {"en": "Format", "zh": "格式"},
    "detail.bitrate": {"en": "Bitrate", "zh": "码率"},
    "detail.sample_rate": {"en": "Sample Rate", "zh": "采样率"},
    "detail.channels": {"en": "Channels", "zh": "声道"},
    "detail.file_size": {"en": "File Size", "zh": "文件大小"},
    "detail.vocal_removed": {"en": "Vocal Removed", "zh": "已去伴奏"},
    "detail.normalized": {"en": "Normalized", "zh": "已标准化"},
    "detail.tags": {"en": "Tags", "zh": "标签"},
    "detail.yes": {"en": "Yes", "zh": "是"},
    "detail.no": {"en": "No", "zh": "否"},
    "detail.none": {"en": "None", "zh": "无"},
}
