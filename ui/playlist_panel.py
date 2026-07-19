"""Playlist panel — browse, manage, and reorder playlists."""

import logging
import tkinter as tk
from tkinter import messagebox, simpledialog

import ttkbootstrap as ttk

from core.formatters import format_duration
from core.i18n import t
from services.library_service import LibraryService
from services.playlist_service import PlaylistService

logger = logging.getLogger(__name__)


class PlaylistPanel(ttk.Frame):
    """Left-right split panel for playlist management."""

    def __init__(
        self,
        parent: tk.Widget,
        playlist_service: PlaylistService,
        library_service: LibraryService,
        on_default_playlist_changed=None,
    ) -> None:
        super().__init__(parent)
        self._playlist_service = playlist_service
        self._library_service = library_service
        self._on_default_playlist_changed = on_default_playlist_changed
        self._playlist_id: int | None = None
        self._playlist_ids: list[int] = []
        self._ref = tk.IntVar(value=25)
        self._build_ui()
        self._load_playlists()

    def _build_ui(self) -> None:
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        left = ttk.Frame(paned, padding=5)
        self._build_left(left)
        paned.add(left, weight=3)
        right = ttk.Frame(paned, padding=5)
        self._build_right(right)
        paned.add(right, weight=7)
    def _build_left(self, p: ttk.Frame) -> None:
        lf = ttk.Frame(p)
        lf.pack(fill=tk.BOTH, expand=True)
        self._playlist_listbox = tk.Listbox(lf, exportselection=False, selectmode=tk.SINGLE)
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self._playlist_listbox.yview)
        self._playlist_listbox.config(yscrollcommand=sb.set)
        self._playlist_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._playlist_listbox.bind("<<ListboxSelect>>", lambda e: self._on_pick())
        bf = ttk.Frame(p)
        bf.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(bf, text=t("playlist.new"), command=self._on_new, bootstyle="success").pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(bf, text=t("playlist.delete"), command=self._on_del, bootstyle="danger").pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text=t("playlist.rename"), command=self._on_ren, bootstyle="secondary").pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text=t("playlist.set_default"), command=self._on_set_default, bootstyle="info").pack(side=tk.LEFT, padx=2)

    def _build_right(self, p: ttk.Frame) -> None:
        self._song_treeat = tk.StringVar(value=t("playlist.no_playlist"))
        ttk.Label(p, textvariable=self._song_treeat, font=("Helvetica", 11, "bold")).pack(fill=tk.X, pady=(0, 5))
        # Song treeview
        tf = ttk.Frame(p)
        tf.pack(fill=tk.BOTH, expand=True)
        self._song_tree = ttk.Treeview(tf, columns=("#", "title", "artist", "duration"),
                                show="headings", selectmode=tk.EXTENDED)
        for c, w, a in zip(("#", "title", "artist", "duration"), (35, 200, 150, 70), (tk.CENTER, tk.W, tk.W, tk.CENTER)):
            hdr = {"#": "#", "title": t("library.title"), "artist": t("library.artist"),
                   "duration": t("library.duration")}.get(c, c)
            self._song_tree.heading(c, text=hdr)
            self._song_tree.column(c, width=w, anchor=a, stretch=c not in ("#", "duration"))
        ssb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self._song_tree.yview)
        self._song_tree.config(yscrollcommand=ssb.set)
        self._song_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ssb.pack(side=tk.RIGHT, fill=tk.Y)
        ctx = tk.Menu(self._song_tree, tearoff=0)
        ctx.add_command(label=t("playlist.remove_from"), command=self._on_rm)
        self._song_tree.bind("<Button-3>", lambda e: self._popup(e))
        self._song_tree.bind("<Button-2>", lambda e: self._popup(e))
        # Reorder buttons
        rf = ttk.Frame(p)
        rf.pack(fill=tk.X, pady=(5, 5))
        ttk.Button(rf, text=t("playlist.move_up"), command=lambda: self._move(-1), bootstyle="secondary").pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(rf, text=t("playlist.move_down"), command=lambda: self._move(1), bootstyle="secondary").pack(side=tk.LEFT, padx=3)
        ttk.Button(rf, text=t("playlist.remove"), command=self._on_rm, bootstyle="danger").pack(side=tk.LEFT, padx=3)
        # Search
        ttk.Separator(p).pack(fill=tk.X, pady=(5, 5))
        sf = ttk.Frame(p)
        sf.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(sf, text=t("playlist.search")).pack(side=tk.LEFT, padx=(0, 5))
        self._search_query = tk.StringVar()
        se = ttk.Entry(sf, textvariable=self._search_query)
        se.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        se.bind("<Return>", lambda e: self._on_search())
        ttk.Button(sf, text=t("playlist.find"), command=self._on_search).pack(side=tk.LEFT)
        # Results treeview
        rf2 = ttk.Frame(p)
        rf2.pack(fill=tk.BOTH, expand=False, pady=(0, 5))
        self._result_tree = ttk.Treeview(rf2, columns=("title", "artist", "duration"),
                                show="headings", selectmode=tk.EXTENDED, height=5)
        for c, w, a in zip(("title", "artist", "duration"), (200, 150, 70), (tk.W, tk.W, tk.CENTER)):
            hdr2 = {"title": t("library.title"), "artist": t("library.artist"),
                    "duration": t("library.duration")}.get(c, c)
            self._result_tree.heading(c, text=hdr2)
            self._result_tree.column(c, width=w, anchor=a, stretch=(c != "duration"))
        rsb = ttk.Scrollbar(rf2, orient=tk.VERTICAL, command=self._result_tree.yview)
        self._result_tree.config(yscrollcommand=rsb.set)
        self._result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rsb.pack(side=tk.RIGHT, fill=tk.Y)
        # Add + reference
        af = ttk.Frame(p)
        af.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(af, text=t("playlist.add_selected"), command=self._on_add, bootstyle="success").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(af, text=t("playlist.add_instrumental"), command=self._on_add_instrumental, bootstyle="info").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(af, text=t("playlist.reference")).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Entry(af, textvariable=self._ref, width=5).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Label(af, text=t("playlist.min")).pack(side=tk.LEFT)
        self._ref.trace_add("write", lambda *_: self._playlist_id is not None and self._load_songs(self._playlist_id))
    def _load_playlists(self) -> None:
        sel = self._playlist_listbox.curselection()
        sid: int | None = None
        if sel and sel[0] < len(self._playlist_ids):
            sid = self._playlist_ids[sel[0]]
        self._playlist_listbox.delete(0, tk.END)
        try:
            playlists = self._playlist_service.get_all()
        except Exception:
            logger.exception("get_all failed")
            messagebox.showerror(t("playlist.error"), t("playlist.error_load"))
            return
        self._playlist_ids = []
        restore = -1
        default_id = self._playlist_service.get_default_playlist_id()
        for pl in playlists:
            self._playlist_ids.append(pl.id)
            label = f"{pl.name} {t('playlist.default_marker')}" if pl.id == default_id else pl.name
            self._playlist_listbox.insert(tk.END, label)
            if pl.id == sid:
                restore = len(self._playlist_ids) - 1
        if restore >= 0:
            self._playlist_listbox.selection_set(restore)
            self._playlist_listbox.see(restore)
    def _load_songs(self, pid: int) -> None:
        try:
            pl = self._playlist_service.get(pid)
            stats = self._playlist_service.get_stats(pid)
            rem = self._playlist_service.get_remaining_time(pid, self._ref.get())
        except Exception:
            logger.exception("load %d failed", pid)
            messagebox.showerror(t("playlist.error"), t("playlist.error_load_songs"))
            return
        self._playlist_id = pid
        for row in self._song_tree.get_children():
            self._song_tree.delete(row)
        for i, item in enumerate(pl.items, 1):
            self._song_tree.insert(
                "", tk.END, iid=str(item.id),
                values=(i, item.title, item.artist, format_duration(item.duration_ms)),
            )
        self._song_treeat.set(
            t("playlist.stats").format(
                name=pl.name, count=stats.song_count,
                total=format_duration(stats.total_duration_ms),
                remaining=format_duration(rem), ref=self._ref.get())
        )
    def _on_pick(self) -> None:
        sel = self._playlist_listbox.curselection()
        if sel and sel[0] < len(self._playlist_ids):
            self._load_songs(self._playlist_ids[sel[0]])
    def _on_set_default(self) -> None:
        selection = self._playlist_listbox.curselection()
        if not selection or selection[0] >= len(self._playlist_ids):
            return
        playlist_id = self._playlist_ids[selection[0]]
        current_default = self._playlist_service.get_default_playlist_id()
        self._playlist_service.set_default_playlist(
            None if current_default == playlist_id else playlist_id
        )
        self._load_playlists()
        if self._on_default_playlist_changed is not None:
            self._on_default_playlist_changed()

    def _on_new(self) -> None:
        name = simpledialog.askstring(
            t("playlist.new_prompt"), t("playlist.new_name"), parent=self)
        if name:
            try:
                self._playlist_service.create(name)
            except Exception:
                logger.exception("create failed")
                messagebox.showerror(t("playlist.error"), "Could not create playlist.")
                return
            self._load_playlists()
    def _on_del(self) -> None:
        sel = self._playlist_listbox.curselection()
        if not sel or sel[0] >= len(self._playlist_ids):
            return
        pid = self._playlist_ids[sel[0]]
        if not messagebox.askyesno(
            t("playlist.confirm_delete"),
            t("playlist.confirm_delete_msg").format(name=self._playlist_listbox.get(sel[0])),
            parent=self,
        ):
            return
        try:
            self._playlist_service.delete(pid)
        except Exception:
            logger.exception("delete %d failed", pid)
            messagebox.showerror(t("playlist.error"), "Could not delete playlist.")
            return
        if self._playlist_id == pid:
            self._playlist_id = None
            for row in self._song_tree.get_children():
                self._song_tree.delete(row)
            self._song_treeat.set(t("playlist.no_playlist"))
        self._load_playlists()
        if self._on_default_playlist_changed is not None:
            self._on_default_playlist_changed()
    def _on_ren(self) -> None:
        sel = self._playlist_listbox.curselection()
        if not sel or sel[0] >= len(self._playlist_ids):
            return
        pid = self._playlist_ids[sel[0]]
        try:
            pl = self._playlist_service.get(pid)
        except Exception:
            logger.exception("get %d failed", pid)
            return
        name = simpledialog.askstring(
            t("playlist.rename_prompt"), t("playlist.rename_name"),
            initialvalue=pl.name, parent=self)
        if name and name != pl.name:
            pl.name = name
            try:
                self._playlist_service.update(pl)
            except Exception:
                logger.exception("update %d failed", pid)
                messagebox.showerror(t("playlist.error"), "Could not rename playlist.")
                return
            self._load_playlists()
            if self._playlist_id is not None:
                self._load_songs(self._playlist_id)
    def _move(self, direction: int) -> None:
        sel = self._song_tree.selection()
        if not sel or self._playlist_id is None:
            return
        order = [int(iid) for iid in self._song_tree.get_children()]
        sels = [int(iid) for iid in sel if int(iid) in order]
        indices = sorted([order.index(s) for s in sels], reverse=(direction > 0))
        for idx in indices:
            ni = idx + direction
            if 0 <= ni < len(order):
                order[idx], order[ni] = order[ni], order[idx]
        try:
            self._playlist_service.reorder_items(self._playlist_id, order)
        except Exception:
            logger.exception("reorder failed")
            messagebox.showerror(t("playlist.error"), "Could not reorder playlist.")
            return
        self._load_songs(self._playlist_id)
    def _on_rm(self) -> None:
        sel = self._song_tree.selection()
        if not sel or self._playlist_id is None:
            return
        for iid in sel:
            try:
                self._playlist_service.remove_item(self._playlist_id, int(iid))
            except Exception:
                logger.exception("remove song %s failed", iid)
                messagebox.showerror(t("playlist.error"), "Could not remove song.")
                return
        self._load_songs(self._playlist_id)
    def _popup(self, event: tk.Event) -> None:
        row = self._song_tree.identify_row(event.y)
        if row:
            if row not in self._song_tree.selection():
                self._song_tree.selection_set(row)
            self._song_tree.tk.call("tk_popup", self._song_tree.children["!menu"], event.x_root, event.y_root)
    def _on_search(self) -> None:
        q = self._search_query.get().strip()
        if not q:
            return
        try:
            results = self._library_service.search(query=q, limit=50)
        except Exception:
            logger.exception("search failed")
            messagebox.showerror(t("playlist.error"), "Could not search library.")
            return
        for row in self._result_tree.get_children():
            self._result_tree.delete(row)
        for s in results:
            self._result_tree.insert("", tk.END, iid=str(s.id),
                            values=(s.title, s.artist, format_duration(s.duration_ms)))
    def _on_add(self) -> None:
        sel = self._result_tree.selection()
        if not sel or self._playlist_id is None:
            return
        try:
            self._playlist_service.add_songs(self._playlist_id, [int(iid) for iid in sel])
        except Exception:
            logger.exception("add songs failed")
            messagebox.showerror(t("playlist.error"), "Could not add songs.")
            return
        self._load_songs(self._playlist_id)
    def _on_add_instrumental(self) -> None:
        sel = self._result_tree.selection()
        if not sel or self._playlist_id is None:
            return
        song_ids = [int(iid) for iid in sel]
        try:
            missing = self._playlist_service.add_instrumentals(
                self._playlist_id, song_ids
            )
        except Exception:
            logger.exception("add instrumentals failed")
            messagebox.showerror(t("playlist.error"), "Could not add instrumentals.")
            return
        if missing:
            messagebox.showinfo(
                t("playlist.error"),
                t("playlist.no_instrumental").format(count=len(missing)),
            )
        self._load_songs(self._playlist_id)

    def refresh(self) -> None:
        """Refresh the entire panel from outside."""
        self._load_playlists()
        if self._playlist_id is not None:
            self._load_songs(self._playlist_id)
