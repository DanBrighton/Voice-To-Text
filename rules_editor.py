import json
import os
import uuid
import tkinter as tk
from tkinter import ttk, messagebox


def _new_rule() -> dict:
    return {
        "id": uuid.uuid4().hex[:10],
        "name": "New rule",
        "enabled": True,
        "match_type": "contains",  # contains | regex
        "pattern": "",
        "actions": [
            {"action": "status", "param": "Rule matched"}
        ],
    }


class RulesEditor(tk.Toplevel):
    """
    A popup editor for rules.json.

    - Displays a list of rules in a Treeview
    - Add/Edit/Delete/Reorder rules
    - Enable/disable toggle
    - Save/Reload
    """
    def __init__(self, master, rules_path: str, on_save_callback=None):
        super().__init__(master)
        self.title("Rules Editor")
        self.geometry("900x500")
        self.transient(master)
        self.grab_set()  # modal-ish

        self.rules_path = rules_path
        self.on_save_callback = on_save_callback

        self.rules = []
        self._build_ui()
        self._load_from_disk()

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        # Left: tree list
        left = ttk.Frame(root)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cols = ("enabled", "name", "match_type", "pattern", "actions")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("enabled", text="Enabled")
        self.tree.heading("name", text="Name")
        self.tree.heading("match_type", text="Match")
        self.tree.heading("pattern", text="Pattern")
        self.tree.heading("actions", text="#Actions")

        self.tree.column("enabled", width=30, anchor="center")
        self.tree.column("name", width=180)
        self.tree.column("match_type", width=90, anchor="center")
        self.tree.column("pattern", width=300)
        self.tree.column("actions", width=70, anchor="center")

        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda e: self._edit_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_buttons())

        # Right: buttons
        right = ttk.Frame(root)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        self.btn_add = ttk.Button(right, text="Add", command=self._add_rule)
        self.btn_edit = ttk.Button(right, text="Edit…", command=self._edit_selected)
        self.btn_toggle = ttk.Button(right, text="Enable/Disable", command=self._toggle_enabled)
        self.btn_delete = ttk.Button(right, text="Delete", command=self._delete_selected)

        self.btn_up = ttk.Button(right, text="Move Up", command=lambda: self._move_selected(-1))
        self.btn_down = ttk.Button(right, text="Move Down", command=lambda: self._move_selected(1))

        ttk.Separator(right).pack(fill=tk.X, pady=10)

        self.btn_reload = ttk.Button(right, text="Reload from disk", command=self._load_from_disk)
        self.btn_save = ttk.Button(right, text="Save", command=self._save_to_disk)
        self.btn_close = ttk.Button(right, text="Close", command=self.destroy)

        for b in [self.btn_add, self.btn_edit, self.btn_toggle, self.btn_delete, self.btn_up, self.btn_down, self.btn_reload, self.btn_save, self.btn_close]:
            b.pack(fill=tk.X, pady=4)

        self._update_buttons()

    def _update_buttons(self):
        has_sel = self._selected_index() is not None
        state = "normal" if has_sel else "disabled"
        self.btn_edit.configure(state=state)
        self.btn_toggle.configure(state=state)
        self.btn_delete.configure(state=state)
        self.btn_up.configure(state=state)
        self.btn_down.configure(state=state)

    def _selected_index(self):
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        try:
            return int(iid)
        except ValueError:
            return None

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(self.rules):
            enabled = "✅" if r.get("enabled", True) else "❌"
            name = r.get("name", "")
            mt = r.get("match_type", "")
            pattern = r.get("pattern", "")
            actions = r.get("actions", []) or []
            self.tree.insert("", "end", iid=str(i), values=(enabled, name, mt, pattern, str(len(actions))))
        self._update_buttons()

    def _load_from_disk(self):
        if not os.path.exists(self.rules_path):
            self.rules = []
            self._refresh_tree()
            return

        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.rules = data if isinstance(data, list) else []
            self._refresh_tree()
        except Exception as e:
            messagebox.showerror("Load failed", f"Could not load rules:\n{e}")
            self.rules = []
            self._refresh_tree()

    def _save_to_disk(self):
        # Basic sanity: rules must be list, each action must have "action"
        for r in self.rules:
            if not r.get("name"):
                messagebox.showerror("Invalid rule", "A rule is missing a name.")
                return
            if not r.get("pattern"):
                messagebox.showerror("Invalid rule", f"Rule '{r.get('name')}' is missing a pattern.")
                return
            for a in r.get("actions", []) or []:
                if not a.get("action"):
                    messagebox.showerror("Invalid action", f"Rule '{r.get('name')}' has an action missing 'action'.")
                    return

        try:
            tmp = self.rules_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, indent=2)
            os.replace(tmp, self.rules_path)
            if self.on_save_callback:
                self.on_save_callback(self.rules)
            messagebox.showinfo("Saved", "Rules saved.")
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save rules:\n{e}")

    def _add_rule(self):
        r = _new_rule()
        if self._open_rule_dialog(r):
            self.rules.append(r)
            self._refresh_tree()

    def _edit_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        r = self.rules[idx]
        # edit in-place via a copy; only apply if OK
        r_copy = json.loads(json.dumps(r))
        if self._open_rule_dialog(r_copy):
            self.rules[idx] = r_copy
            self._refresh_tree()

    def _toggle_enabled(self):
        idx = self._selected_index()
        if idx is None:
            return
        self.rules[idx]["enabled"] = not self.rules[idx].get("enabled", True)
        self._refresh_tree()

    def _delete_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        r = self.rules[idx]
        if messagebox.askyesno("Delete rule", f"Delete '{r.get('name','')}'?"):
            del self.rules[idx]
            self._refresh_tree()

    def _move_selected(self, delta: int):
        idx = self._selected_index()
        if idx is None:
            return
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(self.rules):
            return
        self.rules[idx], self.rules[new_idx] = self.rules[new_idx], self.rules[idx]
        self._refresh_tree()
        self.tree.selection_set(str(new_idx))

    def _open_rule_dialog(self, rule: dict) -> bool:
        dlg = RuleDialog(self, rule)
        self.wait_window(dlg)
        return dlg.result_ok


class RuleDialog(tk.Toplevel):
    """
    Edit a single rule, including its list of actions.
    """
    def __init__(self, master, rule: dict):
        super().__init__(master)
        self.title("Edit Rule")
        self.geometry("700x500")
        self.transient(master)
        self.grab_set()

        self.rule = rule
        self.result_ok = False

        self._build_ui()
        self._load_rule_into_ui()

    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        # Basic fields
        form = ttk.Frame(root)
        form.pack(fill=tk.X)

        self.enabled_var = tk.BooleanVar(value=True)
        self.name_var = tk.StringVar()
        self.match_var = tk.StringVar(value="contains")
        self.pattern_var = tk.StringVar()

        ttk.Checkbutton(form, text="Enabled", variable=self.enabled_var).grid(row=0, column=0, sticky="w")

        ttk.Label(form, text="Name").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.name_var, width=60).grid(row=1, column=1, sticky="we", pady=(8, 0))

        ttk.Label(form, text="Match type").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(form, textvariable=self.match_var, values=["contains", "regex"], state="readonly", width=15).grid(row=2, column=1, sticky="w", pady=(8, 0))

        ttk.Label(form, text="Pattern").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(form, textvariable=self.pattern_var, width=60).grid(row=3, column=1, sticky="we", pady=(8, 0))

        form.columnconfigure(1, weight=1)

        # Actions editor (table)
        ttk.Label(root, text="Actions").pack(anchor="w", pady=(12, 4))

        actions_frame = ttk.Frame(root)
        actions_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("action", "param")
        self.actions_tree = ttk.Treeview(actions_frame, columns=cols, show="headings", selectmode="browse")
        self.actions_tree.heading("action", text="Action")
        self.actions_tree.heading("param", text="Param")
        self.actions_tree.column("action", width=160)
        self.actions_tree.column("param", width=420)
        self.actions_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(actions_frame, command=self.actions_tree.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.actions_tree.configure(yscrollcommand=sb.set)

        # Action controls
        act_controls = ttk.Frame(root)
        act_controls.pack(fill=tk.X, pady=(8, 0))

        ttk.Button(act_controls, text="Add action", command=self._add_action).pack(side=tk.LEFT)
        ttk.Button(act_controls, text="Edit action…", command=self._edit_action).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(act_controls, text="Delete action", command=self._delete_action).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(act_controls, text="Up", command=lambda: self._move_action(-1)).pack(side=tk.LEFT, padx=(20, 0))
        ttk.Button(act_controls, text="Down", command=lambda: self._move_action(1)).pack(side=tk.LEFT, padx=(8, 0))

        # OK/Cancel
        bottom = ttk.Frame(root)
        bottom.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(bottom, text="Cancel", command=self._cancel).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=(0, 8))

    def _load_rule_into_ui(self):
        self.enabled_var.set(bool(self.rule.get("enabled", True)))
        self.name_var.set(self.rule.get("name", ""))
        self.match_var.set(self.rule.get("match_type", "contains"))
        self.pattern_var.set(self.rule.get("pattern", ""))

        self._refresh_actions_tree()

    def _actions_list(self):
        return self.rule.setdefault("actions", [])

    def _refresh_actions_tree(self):
        self.actions_tree.delete(*self.actions_tree.get_children())
        for i, a in enumerate(self._actions_list()):
            self.actions_tree.insert("", "end", iid=str(i), values=(a.get("action", ""), a.get("param", "") or ""))

    def _selected_action_index(self):
        sel = self.actions_tree.selection()
        if not sel:
            return None
        return int(sel[0])

    def _add_action(self):
        a = {"action": "status", "param": "Matched"}
        if ActionDialog(self, a).result_ok:
            self._actions_list().append(a)
            self._refresh_actions_tree()

    def _edit_action(self):
        idx = self._selected_action_index()
        if idx is None:
            return
        a = self._actions_list()[idx]
        a_copy = json.loads(json.dumps(a))
        if ActionDialog(self, a_copy).result_ok:
            self._actions_list()[idx] = a_copy
            self._refresh_actions_tree()

    def _delete_action(self):
        idx = self._selected_action_index()
        if idx is None:
            return
        del self._actions_list()[idx]
        self._refresh_actions_tree()

    def _move_action(self, delta: int):
        idx = self._selected_action_index()
        if idx is None:
            return
        new_idx = idx + delta
        actions = self._actions_list()
        if new_idx < 0 or new_idx >= len(actions):
            return
        actions[idx], actions[new_idx] = actions[new_idx], actions[idx]
        self._refresh_actions_tree()
        self.actions_tree.selection_set(str(new_idx))

    def _ok(self):
        name = self.name_var.get().strip()
        pattern = self.pattern_var.get().strip()
        if not name:
            messagebox.showerror("Invalid rule", "Name is required.")
            return
        if not pattern:
            messagebox.showerror("Invalid rule", "Pattern is required.")
            return
        if not self._actions_list():
            messagebox.showerror("Invalid rule", "At least one action is required.")
            return

        self.rule["enabled"] = bool(self.enabled_var.get())
        self.rule["name"] = name
        self.rule["match_type"] = self.match_var.get().strip().lower()
        self.rule["pattern"] = pattern

        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()


class ActionDialog(tk.Toplevel):
    """
    Edit a single action dict: {"action": "...", "param": "..."}
    """
    def __init__(self, master, action_obj: dict):
        super().__init__(master)
        self.title("Edit Action")
        self.geometry("500x180")
        self.transient(master)
        self.grab_set()

        self.action_obj = action_obj
        self.result_ok = False

        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        self.action_var = tk.StringVar(value=action_obj.get("action", "status"))
        self.param_var = tk.StringVar(value=action_obj.get("param", "") or "")

        ttk.Label(root, text="Action").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            root,
            textvariable=self.action_var,
            values=["status", "pause", "resume", "stop", "log"],
            state="readonly",
            width=20,
        ).grid(row=0, column=1, sticky="w")

        ttk.Label(root, text="Param").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(root, textvariable=self.param_var, width=50).grid(row=1, column=1, sticky="we", pady=(8, 0))

        root.columnconfigure(1, weight=1)

        bottom = ttk.Frame(root)
        bottom.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))

        ttk.Button(bottom, text="Cancel", command=self._cancel).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=(0, 8))

        self.wait_window(self)

    def _ok(self):
        action = self.action_var.get().strip().lower()
        param = self.param_var.get().strip()

        if not action:
            messagebox.showerror("Invalid action", "Action is required.")
            return

        # param is optional; clear it for actions like pause/resume/stop
        if action in ("pause", "resume", "stop"):
            param = ""

        self.action_obj["action"] = action
        self.action_obj["param"] = param if param else None

        self.result_ok = True
        self.destroy()

    def _cancel(self):
        self.result_ok = False
        self.destroy()