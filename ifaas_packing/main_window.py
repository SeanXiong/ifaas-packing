from __future__ import annotations

from functools import partial
from typing import Any, Callable

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRunnable, QSize, QStringListModel, Qt, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QListWidgetItem,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    EditableComboBox,
    FluentIcon as FIF,
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    NavigationItemPosition,
    PasswordLineEdit,
    Pivot,
    PrimaryPushButton,
    ProgressBar,
    ProgressRing,
    PushButton,
    RadioButton,
    SearchLineEdit,
    StrongBodyLabel,
    SubtitleLabel,
    SwitchButton,
    Theme,
    TransparentToolButton,
    setTheme,
)

from .api import ApiClient
from .storage import CredentialStore, FavoriteStore


def pick(data: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def object_id(data: dict[str, Any]) -> str:
    return pick(data, "id", "pk", "project_id", "version_id")


def module_id(data: dict[str, Any]) -> str:
    return pick(data, "pk", "id")


def module_git_url(data: dict[str, Any]) -> str:
    git_url = data.get("git_url")
    if isinstance(git_url, dict):
        return pick(git_url, "git_url", "url")
    if git_url not in (None, ""):
        return str(git_url)
    return pick(data, "git", "repository", "repo_url")


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)


class Worker(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            self.signals.finished.emit(self.fn())
        except Exception as exc:  # noqa: BLE001 - 线程边界统一转换为 UI 提示。
            self.signals.failed.emit(str(exc))


class LoginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("登录项目打包客户端")
        self.resize(430, 330)
        self.thread_pool = QThreadPool.globalInstance()
        self.credential_store = CredentialStore()
        self.api_client: ApiClient | None = None

        saved = self.credential_store.load()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(14)

        layout.addWidget(SubtitleLabel("项目打包客户端"))
        hint = BodyLabel("请输入账号密码登录后继续")
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)

        self.username_edit = LineEdit()
        self.username_edit.setPlaceholderText("账号")
        self.username_edit.setClearButtonEnabled(True)
        self.username_edit.setText(str(saved.get("username") or ""))

        self.password_edit = PasswordLineEdit()
        self.password_edit.setPlaceholderText("密码")
        self.password_edit.setClearButtonEnabled(True)
        self.password_edit.setText(str(saved.get("password") or ""))

        self.remember_checkbox = CheckBox("记住账号密码")
        self.remember_checkbox.setChecked(bool(saved.get("remember")))

        self.login_button = PrimaryPushButton("登录")
        self.login_button.setIcon(FIF.ACCEPT)
        self.login_button.clicked.connect(self.login)
        self.password_edit.returnPressed.connect(self.login)
        self.username_edit.returnPressed.connect(self.login)

        layout.addWidget(BodyLabel("账号"))
        layout.addWidget(self.username_edit)
        layout.addWidget(BodyLabel("密码"))
        layout.addWidget(self.password_edit)
        layout.addWidget(self.remember_checkbox)
        layout.addStretch()
        layout.addWidget(self.login_button)

    def run_task(self, fn: Callable[[], Any], on_success: Callable[[Any], None], error_title: str) -> None:
        worker = Worker(fn)
        worker.signals.finished.connect(on_success)
        worker.signals.failed.connect(lambda message: self.show_error(error_title, message))
        self.thread_pool.start(worker)

    def login(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            self.show_error("登录失败", "请输入账号和密码。")
            return

        self.login_button.setEnabled(False)
        self.login_button.setText("登录中...")
        client = ApiClient(username=username, password=password)
        self.run_task(lambda: self._login_client(client), self._on_login_success, "登录失败")

    def _login_client(self, client: ApiClient) -> ApiClient:
        client.login()
        return client

    def _on_login_success(self, client: ApiClient) -> None:
        self.api_client = client
        self.credential_store.save(
            client.username,
            client.password,
            self.remember_checkbox.isChecked(),
        )
        self.accept()

    def show_error(self, title: str, content: str) -> None:
        self.login_button.setEnabled(True)
        self.login_button.setText("登录")
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
            parent=self,
        )


class ProjectRow(QWidget):
    clicked = pyqtSignal(dict)
    favorite_toggled = pyqtSignal(dict)

    def __init__(self, project: dict[str, Any], favorited: bool) -> None:
        super().__init__()
        self.project = project
        self.setObjectName("ProjectRow")

        self.name_label = StrongBodyLabel(pick(project, "name", "project_name", "title", default="未命名项目"))
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.favorite_button = TransparentToolButton(FIF.HEART)
        self.favorite_button.setFixedSize(34, 34)
        self.favorite_button.setToolTip("收藏 / 取消收藏")
        self.favorite_button.clicked.connect(lambda: self.favorite_toggled.emit(self.project))
        self.set_favorited(favorited)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 6, 6)
        layout.setSpacing(8)
        layout.addWidget(self.name_label, 1)
        layout.addWidget(self.favorite_button)

    def set_favorited(self, favorited: bool) -> None:
        self.favorite_button.setText("★" if favorited else "☆")

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self.project)
        super().mousePressEvent(event)


class VersionRow(QWidget):
    clicked = pyqtSignal(dict)

    def __init__(self, version: dict[str, Any]) -> None:
        super().__init__()
        self.version = version
        self.setObjectName("VersionRow")

        version_name = pick(version, "update_version", default="未命名版本")
        created = pick(version, "created", "create_time", "created_at", "ctime", default="-")

        title = StrongBodyLabel(version_name)
        title.setWordWrap(True)
        created_label = BodyLabel(f"创建时间：{created}")
        created_label.setObjectName("MutedLabel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        layout.addWidget(title)
        layout.addWidget(created_label)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit(self.version)
        super().mousePressEvent(event)


class ModuleRow(QWidget):
    branch_change_requested = pyqtSignal(object)

    def __init__(self, module: dict[str, Any]) -> None:
        super().__init__()
        self.module = module
        self.setObjectName("ModuleRow")

        self.checkbox = CheckBox()
        self.checkbox.setChecked(False)

        self.name_label = StrongBodyLabel(pick(module, "name", "module_name", default="未命名服务"))
        self.name_label.setWordWrap(True)
        self.branch_label = BodyLabel(pick(module, "branch", "ref_name", "git_branch", "tag", default="-"))
        self.branch_label.setObjectName("MutedLabel")

        self.branch_button = TransparentToolButton(FIF.EDIT)
        self.branch_button.setFixedSize(34, 34)
        self.branch_button.setToolTip("修改分支")
        self.branch_button.clicked.connect(lambda: self.branch_change_requested.emit(self))

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)
        text_layout.addWidget(self.name_label)
        text_layout.addWidget(self.branch_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(self.checkbox)
        layout.addLayout(text_layout, 1)
        layout.addWidget(self.branch_button)

    def set_branch(self, branch: str) -> None:
        self.module["branch"] = branch
        self.branch_label.setText(branch)

    def matches(self, keyword: str) -> bool:
        text = (
            pick(self.module, "name", "module_name")
            + " "
            + pick(self.module, "branch", "ref_name", "git_branch", "tag")
        ).lower()
        return keyword.lower() in text

    def selected_payload(self, need_apollo: bool) -> dict[str, Any] | None:
        if not self.checkbox.isChecked():
            return None
        name = pick(self.module, "name", "module_name")
        return {
            "need_apollo": need_apollo,
            "ref_name": pick(self.module, "branch", "ref_name", "git_branch", "tag"),
            "pk": self.module.get("pk", self.module.get("id")),
            "name": name,
            "custom_name": name,
        }


class BranchDialog(QDialog):
    def __init__(self, service_name: str, refs: dict[str, Any], current_branch: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("修改分支")
        self.resize(520, 190)

        data = refs.get("data", refs) if isinstance(refs, dict) else {}
        branches = data.get("branches", []) if isinstance(data, dict) else []
        tags = data.get("tags", []) if isinstance(data, dict) else []
        refs_options = [str(item) for item in branches] + [str(item) for item in tags]

        self.branch_combo = EditableComboBox()
        self.branch_combo.addItems([str(item) for item in branches])
        if tags:
            self.branch_combo.insertSeparator(self.branch_combo.count())
            self.branch_combo.addItems([str(item) for item in tags])
        self.completer_model = QStringListModel(refs_options, self)
        self.completer = QCompleter(self.completer_model, self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.branch_combo.setCompleter(self.completer)
        if current_branch:
            index = self.branch_combo.findText(current_branch)
            if index >= 0:
                self.branch_combo.setCurrentIndex(index)
            else:
                self.branch_combo.setEditText(current_branch)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel(service_name))
        layout.addWidget(BodyLabel("选择或输入目标分支"))
        layout.addWidget(self.branch_combo)
        layout.addWidget(buttons)

    def selected_branch(self) -> str:
        return self.branch_combo.currentText().strip()


class PackageRecordRow(QWidget):
    copy_requested = pyqtSignal(str, str)
    upload_requested = pyqtSignal(object)

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__()
        self.record = record
        self.setObjectName("PackageRecordRow")

        created_time = pick(record, "created_time", default="-")
        support_cpu = pick(record, "support_cpu", default="-")
        status = self._status_text(record.get("pack_status"))
        download_path = pick(record, "download_path", default="-")
        seafile_path = pick(record, "seafile_path", default="-")
        has_seafile = bool(seafile_path and seafile_path != "-")

        title = StrongBodyLabel(f"打包时间：{created_time}")
        meta = BodyLabel(f"架构：{support_cpu}    状态：{status}")
        meta.setObjectName("MutedLabel")

        intranet_label = BodyLabel(f"内网：{download_path}")
        intranet_label.setObjectName("MutedLabel")
        extranet_label = BodyLabel(f"外网：{seafile_path}")
        extranet_label.setObjectName("MutedLabel")

        self.copy_intranet_button = TransparentToolButton(FIF.COPY)
        self.copy_intranet_button.setFixedSize(32, 32)
        self.copy_intranet_button.setToolTip("复制内网下载地址")
        self.copy_intranet_button.clicked.connect(lambda: self.copy_requested.emit("内网下载地址", download_path))

        self.copy_extranet_button = TransparentToolButton(FIF.COPY)
        self.copy_extranet_button.setFixedSize(32, 32)
        self.copy_extranet_button.setToolTip("复制外网下载地址")
        self.copy_extranet_button.clicked.connect(lambda: self.copy_requested.emit("外网下载地址", seafile_path))

        self.upload_button = PushButton("上传网盘")
        self.upload_button.setIcon(FIF.CLOUD)
        self.upload_button.clicked.connect(lambda: self.upload_requested.emit(self))
        self.upload_button.setVisible(not has_seafile)

        self.progress_label = BodyLabel("等待上传")
        self.progress_label.setObjectName("MutedLabel")
        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_label.hide()
        self.progress_bar.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addWidget(meta)

        intranet_row = QHBoxLayout()
        intranet_row.setContentsMargins(0, 0, 0, 0)
        intranet_row.addWidget(intranet_label, 1)
        intranet_row.addWidget(self.copy_intranet_button)

        extranet_row = QHBoxLayout()
        extranet_row.setContentsMargins(0, 0, 0, 0)
        extranet_row.addWidget(extranet_label, 1)
        if has_seafile:
            extranet_row.addWidget(self.copy_extranet_button)
        else:
            extranet_row.addWidget(self.upload_button)

        layout.addLayout(intranet_row)
        layout.addLayout(extranet_row)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

    def storage_path(self) -> str:
        return pick(self.record, "storage_path")

    def set_uploading(self, uploading: bool) -> None:
        self.upload_button.setEnabled(not uploading)
        self.progress_label.setVisible(uploading)
        self.progress_bar.setVisible(uploading)
        if uploading:
            self.progress_label.setText("正在上传网盘...")
            self.progress_bar.setValue(0)

    def update_upload_progress(self, progress: dict[str, Any]) -> None:
        percent = progress.get("percent", 0) if isinstance(progress, dict) else 0
        try:
            value = max(0, min(100, int(float(percent))))
        except (TypeError, ValueError):
            value = 0
        speed = progress.get("speed") if isinstance(progress, dict) else None
        description = progress.get("description") if isinstance(progress, dict) else None
        suffix = f" · {speed}" if speed else ""
        self.progress_bar.setValue(value)
        self.progress_label.setText(f"{description or '正在上传网盘'}：{percent}%{suffix}")

    def set_upload_finished(self, success: bool) -> None:
        self.progress_bar.setValue(100 if success else self.progress_bar.value())
        self.progress_label.setText("上传完成" if success else "上传失败")
        self.upload_button.setEnabled(not success)
        self.upload_button.setVisible(not success)

    @staticmethod
    def _status_text(status: Any) -> str:
        status_map = {
            0: "等待中",
            1: "成功",
            2: "失败",
            3: "执行中",
        }
        return status_map.get(status, str(status if status is not None else "-"))


class PackageRecordsDialog(QDialog):
    rows_closing = pyqtSignal(list)

    def __init__(
        self,
        version_name: str,
        records: list[dict[str, Any]],
        copy_handler: Callable[[str, str], None],
        upload_handler: Callable[[PackageRecordRow], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("当前版本升级包")
        self.resize(780, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel("当前版本升级包"))
        hint = BodyLabel(f"{version_name}    共 {len(records)} 条记录")
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)

        self.record_list = ListWidget()
        layout.addWidget(self.record_list, 1)

        if not records:
            self.record_list.addItem("当前版本暂无升级包记录")
        else:
            self.record_rows: list[PackageRecordRow] = []
            for record in records:
                item = QListWidgetItem()
                row = PackageRecordRow(record)
                self.record_rows.append(row)
                row.copy_requested.connect(copy_handler)
                row.upload_requested.connect(upload_handler)
                item.setSizeHint(QSize(700, 132))
                self.record_list.addItem(item)
                self.record_list.setItemWidget(item, row)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.rows_closing.emit(getattr(self, "record_rows", []))
        super().closeEvent(event)

    def reject(self) -> None:  # type: ignore[override]
        self.rows_closing.emit(getattr(self, "record_rows", []))
        super().reject()


class PackingInterface(QWidget):
    def __init__(self, api_client: ApiClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("packingInterface")
        self.api = api_client
        self.favorites = FavoriteStore()
        self.thread_pool = QThreadPool.globalInstance()
        self.projects: list[dict[str, Any]] = []
        self.current_project: dict[str, Any] | None = None
        self.current_version: dict[str, Any] | None = None
        self.module_rows: list[ModuleRow] = []
        self.upload_tasks: dict[str, PackageRecordRow] = {}
        self.records_dialog: PackageRecordsDialog | None = None
        self.project_tab = "favorite"

        self._build_ui()
        self._wire_events()
        self.show_info("登录成功", "正在加载项目...")
        self.load_projects()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_area = QVBoxLayout()
        title_area.setContentsMargins(0, 0, 0, 0)
        title_area.setSpacing(2)
        title_area.addWidget(SubtitleLabel("项目打包工作台"))
        title_area.addWidget(BodyLabel("三栏联动选择项目、版本与服务组件"))
        header.addLayout(title_area, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(10)
        splitter.addWidget(self._build_project_card())
        splitter.addWidget(self._build_version_card())
        splitter.addWidget(self._build_pack_card())
        splitter.setSizes([360, 390, 690])

        root.addLayout(header)
        root.addWidget(splitter, 1)

    def _build_project_card(self) -> CardWidget:
        card = CardWidget()
        card.setObjectName("ProjectCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel("项目管理"))

        self.project_search = SearchLineEdit()
        self.project_search.setPlaceholderText("搜索项目...")
        layout.addWidget(self.project_search)

        self.project_pivot = Pivot()
        self.project_pivot.addItem("favorite", "我的收藏", partial(self.switch_project_tab, "favorite"))
        self.project_pivot.addItem("all", "全量项目", partial(self.switch_project_tab, "all"))
        self.project_pivot.setCurrentItem("favorite")
        layout.addWidget(self.project_pivot)

        self.favorite_list = ListWidget()
        self.all_project_list = ListWidget()
        self.all_project_list.hide()
        layout.addWidget(self.favorite_list, 1)
        layout.addWidget(self.all_project_list, 1)
        return card

    def _build_version_card(self) -> CardWidget:
        card = CardWidget()
        card.setObjectName("VersionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel("版本选择"))
        self.version_hint = BodyLabel("请选择左侧项目")
        self.version_hint.setObjectName("MutedLabel")
        layout.addWidget(self.version_hint)

        self.version_list = ListWidget()
        layout.addWidget(self.version_list, 1)
        return card

    def _build_pack_card(self) -> CardWidget:
        card = CardWidget()
        card.setObjectName("PackCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title_row = QHBoxLayout()
        title_text = QVBoxLayout()
        title_text.setContentsMargins(0, 0, 0, 0)
        title_text.setSpacing(2)
        title_text.addWidget(SubtitleLabel("组件配置与打包"))
        self.package_hint = BodyLabel("请选择中间栏版本")
        self.package_hint.setObjectName("MutedLabel")
        title_text.addWidget(self.package_hint)
        self.module_loading_ring = ProgressRing()
        self.module_loading_ring.setFixedSize(28, 28)
        self.module_loading_ring.hide()
        title_row.addLayout(title_text, 1)
        title_row.addWidget(self.module_loading_ring)
        layout.addLayout(title_row)

        layout.addWidget(self._build_global_form())
        layout.addWidget(self._build_module_card(), 1)

        actions = QHBoxLayout()
        self.records_button = PushButton("查看升级包")
        self.records_button.setIcon(FIF.DOWNLOAD)
        self.records_button.setEnabled(False)
        self.cancel_button = PushButton("取消")
        self.cancel_button.setIcon(FIF.CANCEL)
        self.pack_button = PrimaryPushButton("开始打包")
        self.pack_button.setIcon(FIF.PLAY)
        self.pack_button.setEnabled(False)
        actions.addWidget(self.records_button)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.pack_button)
        layout.addLayout(actions)
        return card

    def _build_global_form(self) -> CardWidget:
        card = CardWidget()
        card.setObjectName("FormCard")
        layout = QGridLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(12)

        layout.addWidget(StrongBodyLabel("全局参数"), 0, 0, 1, 4)

        layout.addWidget(BodyLabel("升级包类型"), 1, 0)
        self.offline_radio = RadioButton("离线升级包")
        self.online_radio = RadioButton("在线升级包")
        self.offline_radio.setChecked(True)
        self.package_type_group = QButtonGroup(self)
        self.package_type_group.addButton(self.offline_radio)
        self.package_type_group.addButton(self.online_radio)
        radio_row = QHBoxLayout()
        radio_row.setContentsMargins(0, 0, 0, 0)
        radio_row.addWidget(self.offline_radio)
        radio_row.addWidget(self.online_radio)
        radio_row.addStretch()
        layout.addLayout(radio_row, 1, 1, 1, 3)

        layout.addWidget(BodyLabel("CPU架构"), 2, 0)
        self.cpu_combo = ComboBox()
        self.cpu_combo.addItems(["x86_64", "aarch64"])
        layout.addWidget(self.cpu_combo, 2, 1)

        layout.addWidget(BodyLabel("上传云盘"), 2, 2)
        self.seafile_switch = SwitchButton()
        self.seafile_switch.setChecked(False)
        layout.addWidget(self.seafile_switch, 2, 3)

        layout.addWidget(BodyLabel("命名空间"), 3, 0)
        self.namespace_edit = LineEdit()
        self.namespace_edit.setText("basic-app")
        self.namespace_edit.setClearButtonEnabled(True)
        layout.addWidget(self.namespace_edit, 3, 1)

        layout.addWidget(BodyLabel("Apollo数据库"), 3, 2)
        self.apollo_edit = LineEdit()
        self.apollo_edit.setPlaceholderText("服务器 IP，留空则不启用")
        self.apollo_edit.setClearButtonEnabled(True)
        layout.addWidget(self.apollo_edit, 3, 3)
        return card

    def _build_module_card(self) -> CardWidget:
        card = CardWidget()
        card.setObjectName("ModuleCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        tools = QHBoxLayout()
        self.select_all_modules = CheckBox("全选")
        self.select_all_modules.setChecked(True)
        self.module_search = SearchLineEdit()
        self.module_search.setPlaceholderText("过滤服务...")
        tools.addWidget(self.select_all_modules)
        tools.addWidget(self.module_search, 1)

        self.module_list = ListWidget()
        layout.addWidget(StrongBodyLabel("业务组件"))
        layout.addLayout(tools)
        layout.addWidget(self.module_list, 1)
        return card

    def _wire_events(self) -> None:
        self.project_search.textChanged.connect(self._debounced_project_search)
        self.project_search.returnPressed.connect(self.load_projects)
        if hasattr(self.project_search, "searchSignal"):
            self.project_search.searchSignal.connect(self.load_projects)

        self.module_search.textChanged.connect(self.filter_modules)
        self.select_all_modules.stateChanged.connect(self._set_all_modules)
        self.pack_button.clicked.connect(self.submit_pack)
        self.cancel_button.clicked.connect(self.clear_modules)
        self.records_button.clicked.connect(self.load_update_records)

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.load_projects)

        self.upload_progress_timer = QTimer(self)
        self.upload_progress_timer.setInterval(2000)
        self.upload_progress_timer.timeout.connect(self.poll_upload_progress)

    def run_task(self, fn: Callable[[], Any], on_success: Callable[[Any], None], error_title: str) -> None:
        worker = Worker(fn)
        worker.signals.finished.connect(on_success)
        worker.signals.failed.connect(lambda message: self.show_error(error_title, message))
        self.thread_pool.start(worker)

    def show_info(self, title: str, content: str) -> None:
        InfoBar.info(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2400,
            parent=self.window(),
        )

    def show_success(self, title: str, content: str) -> None:
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self.window(),
        )

    def show_error(self, title: str, content: str) -> None:
        self.set_module_loading(False)
        if hasattr(self, "records_button"):
            self.records_button.setEnabled(bool(self.current_version))
            self.records_button.setText("查看升级包")
        self.pack_button.setEnabled(bool(self.current_version and self.module_rows))
        for row in self.module_rows:
            row.branch_button.setEnabled(True)
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
            parent=self.window(),
        )

    def _debounced_project_search(self) -> None:
        self.search_timer.start()

    def switch_project_tab(self, tab: str) -> None:
        self.project_tab = tab
        self.favorite_list.setVisible(tab == "favorite")
        self.all_project_list.setVisible(tab == "all")
        self.project_pivot.setCurrentItem(tab)
        self.render_projects()

    def load_projects(self) -> None:
        keyword = self.project_search.text().strip()
        self.run_task(lambda: self.api.search_projects(keyword), self._on_projects_loaded, "项目查询失败")

    def _on_projects_loaded(self, projects: list[dict[str, Any]]) -> None:
        self.projects = projects
        self.render_projects()
        self.show_info("项目已加载", f"共 {len(projects)} 个项目")

    def render_projects(self) -> None:
        self.favorite_list.clear()
        self.all_project_list.clear()
        favorites = self.favorites.all()
        for project in self.projects:
            pid = object_id(project)
            favorited = pid in favorites
            self._add_project_row(self.all_project_list, project, favorited)
            if favorited:
                self._add_project_row(self.favorite_list, project, favorited)

    def _add_project_row(self, list_widget: ListWidget, project: dict[str, Any], favorited: bool) -> None:
        item = QListWidgetItem()
        row = ProjectRow(project, favorited)
        row.clicked.connect(self.select_project)
        row.favorite_toggled.connect(self.toggle_favorite)
        item.setSizeHint(QSize(260, 54))
        list_widget.addItem(item)
        list_widget.setItemWidget(item, row)

    def toggle_favorite(self, project: dict[str, Any]) -> None:
        pid = object_id(project)
        if not pid:
            self.show_error("收藏失败", "当前项目缺少 id/pk 字段，无法持久化收藏。")
            return
        favorited = self.favorites.toggle(pid)
        self.render_projects()
        action = "已收藏" if favorited else "已取消收藏"
        self.show_success("收藏状态已更新", f"{action}：{pick(project, 'name', 'project_name', default=pid)}")

    def select_project(self, project: dict[str, Any]) -> None:
        self.current_project = project
        self.current_version = None
        self.version_list.clear()
        self.clear_modules()
        self.records_button.setEnabled(False)

        project_name = pick(project, "name", "project_name", default="当前项目")
        self.version_hint.setText(f"当前项目：{project_name}")
        project_id = object_id(project)
        if not project_id:
            self.show_error("版本查询失败", "当前项目缺少 id/pk 字段。")
            return
        self.run_task(lambda: self.api.get_versions(project_id), self._on_versions_loaded, "版本查询失败")

    def _on_versions_loaded(self, versions: list[dict[str, Any]]) -> None:
        self.version_list.clear()
        for version in versions:
            item = QListWidgetItem()
            row = VersionRow(version)
            row.clicked.connect(self.select_version)
            item.setSizeHint(QSize(300, 68))
            self.version_list.addItem(item)
            self.version_list.setItemWidget(item, row)
        self.show_info("版本已加载", f"共 {len(versions)} 个版本")

    def select_version(self, version: dict[str, Any]) -> None:
        self.current_version = version
        self.clear_modules()
        version_name = pick(version, "update_version", default="当前版本")
        self.package_hint.setText(f"当前版本：{version_name}")
        version_id = object_id(version)
        if not version_id:
            self.show_error("组件查询失败", "当前版本缺少 id/pk 字段。")
            return
        self.records_button.setEnabled(True)
        self.set_module_loading(True)
        self.run_task(lambda: self.api.get_modules(version_id), self._on_modules_loaded, "组件查询失败")

    def _on_modules_loaded(self, modules: list[dict[str, Any]]) -> None:
        self.set_module_loading(False)
        self.clear_modules()
        for module in modules:
            row = ModuleRow(module)
            row.checkbox.stateChanged.connect(self._sync_select_all_state)
            row.branch_change_requested.connect(self.change_module_branch)
            self.module_rows.append(row)

            item = QListWidgetItem()
            item.setSizeHint(QSize(420, 62))
            self.module_list.addItem(item)
            self.module_list.setItemWidget(item, row)

        self.select_all_modules.setChecked(False)
        self.pack_button.setEnabled(bool(self.current_version and modules))
        self.show_info("服务已加载", f"共 {len(modules)} 个服务组件")

    def load_update_records(self) -> None:
        if not self.current_version:
            self.show_error("升级包查询失败", "请先选择一个版本。")
            return
        version_id = object_id(self.current_version)
        if not version_id:
            self.show_error("升级包查询失败", "当前版本缺少 id/pk 字段。")
            return
        self.records_button.setEnabled(False)
        self.records_button.setText("查询中...")
        self.run_task(
            lambda: self.api.get_update_records(version_id, True),
            self._on_update_records_loaded,
            "升级包查询失败",
        )

    def _on_update_records_loaded(self, records: list[dict[str, Any]]) -> None:
        self.records_button.setEnabled(True)
        self.records_button.setText("查看升级包")
        version_name = pick(self.current_version or {}, "update_version", default="当前版本")
        self.records_dialog = PackageRecordsDialog(
            version_name,
            records,
            self.copy_download_url,
            self.upload_record_to_seafile,
            self,
        )
        self.records_dialog.rows_closing.connect(self.cancel_upload_tasks_for_rows)
        self.records_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.records_dialog.exec()

    def copy_download_url(self, label: str, url: str) -> None:
        if not url or url == "-":
            self.show_error("复制失败", f"{label}为空。")
            return
        QApplication.clipboard().setText(url)
        self.show_success("复制成功", f"已复制{label}")

    def upload_record_to_seafile(self, row: PackageRecordRow) -> None:
        storage_path = row.storage_path()
        if not storage_path:
            self.show_error("上传失败", "当前记录缺少 storage_path，无法上传网盘。")
            return
        row.set_uploading(True)
        self.run_task(
            lambda: self.api.upload_to_seafile(storage_path),
            lambda result: self._on_upload_started(row, result),
            "上传网盘失败",
        )

    def _on_upload_started(self, row: PackageRecordRow, result: dict[str, Any]) -> None:
        if self._row_deleted(row):
            return
        success = result.get("success")
        task_id = result.get("taskID") or result.get("task_id")
        if not success or not task_id:
            row.set_upload_finished(False)
            self.show_error("上传网盘失败", str(result.get("message") or "上传任务创建失败。"))
            return

        task_id = str(task_id)
        self.upload_tasks[task_id] = row
        self.upload_progress_timer.start()
        row.progress_label.setText("上传任务已触发，正在获取进度...")
        self.show_info("上传已触发", f"任务 ID：{task_id}")

    def poll_upload_progress(self) -> None:
        if not self.upload_tasks:
            self.upload_progress_timer.stop()
            return
        for task_id in list(self.upload_tasks):
            self.run_task(
                lambda task_id=task_id: self.api.get_upload_progress(task_id),
                lambda result, task_id=task_id: self._on_upload_progress(task_id, result),
                "上传进度查询失败",
            )

    def _on_upload_progress(self, task_id: str, result: dict[str, Any]) -> None:
        row = self.upload_tasks.get(task_id)
        if not row:
            return
        if self._row_deleted(row):
            self.upload_tasks.pop(task_id, None)
            if not self.upload_tasks:
                self.upload_progress_timer.stop()
            return

        progress = result.get("progress", {})
        if isinstance(progress, dict):
            row.update_upload_progress(progress)

        complete = bool(result.get("complete"))
        if complete:
            success = bool(result.get("success"))
            row.set_upload_finished(success)
            self.upload_tasks.pop(task_id, None)
            if not self.upload_tasks:
                self.upload_progress_timer.stop()
            if success:
                self.show_success("上传完成", "网盘上传任务已完成，可稍后刷新升级包记录查看外网地址。")
            else:
                self.show_error("上传失败", "网盘上传任务执行失败。")

    def cancel_upload_tasks_for_rows(self, rows: list[PackageRecordRow]) -> None:
        row_ids = {id(row) for row in rows}
        for task_id, row in list(self.upload_tasks.items()):
            if id(row) in row_ids or self._row_deleted(row):
                self.upload_tasks.pop(task_id, None)
        if not self.upload_tasks:
            self.upload_progress_timer.stop()

    @staticmethod
    def _row_deleted(row: PackageRecordRow) -> bool:
        try:
            return sip.isdeleted(row) or sip.isdeleted(row.progress_bar)
        except RuntimeError:
            return True

    def set_module_loading(self, loading: bool) -> None:
        self.module_loading_ring.setVisible(loading)
        self.select_all_modules.setEnabled(not loading)
        self.module_search.setEnabled(not loading)
        self.pack_button.setText("正在提交..." if loading and not self.module_rows else "开始打包")
        self.pack_button.setEnabled(False if loading else bool(self.current_version and self.module_rows))

    def clear_modules(self) -> None:
        self.pack_button.setEnabled(False)
        self.module_rows = []
        self.module_list.clear()

    def filter_modules(self, keyword: str) -> None:
        keyword = keyword.strip()
        for index, row in enumerate(self.module_rows):
            self.module_list.item(index).setHidden(not row.matches(keyword))
        self._sync_select_all_state()

    def _set_all_modules(self, state: int) -> None:
        checked = state == Qt.CheckState.Checked.value
        for index, row in enumerate(self.module_rows):
            if not self.module_list.item(index).isHidden():
                row.checkbox.blockSignals(True)
                row.checkbox.setChecked(checked)
                row.checkbox.blockSignals(False)

    def _sync_select_all_state(self) -> None:
        visible_rows = [
            row
            for index, row in enumerate(self.module_rows)
            if not self.module_list.item(index).isHidden()
        ]
        if not visible_rows:
            return
        all_checked = all(row.checkbox.isChecked() for row in visible_rows)
        self.select_all_modules.blockSignals(True)
        self.select_all_modules.setChecked(all_checked)
        self.select_all_modules.blockSignals(False)

    def change_module_branch(self, row: ModuleRow) -> None:
        git_url = module_git_url(row.module)
        if not git_url:
            self.show_error("无法修改分支", "当前服务缺少 git_url.git_url 字段。")
            return

        row.branch_button.setEnabled(False)
        self.run_task(
            lambda: self.api.get_refs(git_url),
            lambda refs: self._open_branch_dialog(row, git_url, refs),
            "获取分支失败",
        )

    def _open_branch_dialog(self, row: ModuleRow, git_url: str, refs: dict[str, Any]) -> None:
        row.branch_button.setEnabled(True)
        service_name = pick(row.module, "name", "module_name", default="当前服务")
        current_branch = pick(row.module, "branch", "ref_name", "git_branch", "tag")
        dialog = BranchDialog(service_name, refs, current_branch, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        branch = dialog.selected_branch()
        if not branch:
            self.show_error("无法修改分支", "目标分支不能为空。")
            return

        row.branch_button.setEnabled(False)
        self.run_task(
            lambda: self._update_module_branch(row.module, git_url, branch),
            lambda result: self._on_module_branch_updated(row, branch, result),
            "修改分支失败",
        )

    def _update_module_branch(self, module: dict[str, Any], git_url: str, branch: str) -> dict[str, Any]:
        config = self.api.get_git_config(git_url, branch)
        config_data = config.get("data", config)
        if not isinstance(config_data, dict):
            raise RuntimeError("git_config 接口返回数据格式异常。")
        git_id = config_data.get("git_id")
        if not git_id:
            raise RuntimeError("git_config 接口未返回 git_id。")

        git_messages = config_data.get("git_message", [])
        first_message = git_messages[0] if isinstance(git_messages, list) and git_messages else {}
        if not isinstance(first_message, dict):
            first_message = {}

        service_name = pick(first_message, "service_name") or pick(module, "name", "module_name")
        payload = {
            "name": service_name,
            "custom_name": service_name,
            "service_type": module.get("service_type", 1),
            "branch": branch,
            "APP_ID": module.get("APP_ID") or service_name,
            "git_config_path": pick(first_message, "git_config_path")
            or pick(module, "git_config_path", default="build_ci/config.yml"),
            "is_image": module.get("is_image", True),
            "version": object_id(self.current_version or {}),
            "git_url": git_id,
        }

        mid = module_id(module)
        if not mid:
            raise RuntimeError("当前服务缺少 pk/id 字段，无法提交修改。")
        result = self.api.update_module(mid, payload)
        result_code = result.get("resultCode")
        if result_code not in (None, 0):
            raise RuntimeError(str(result.get("message") or "修改服务分支失败。"))
        return result

    def _on_module_branch_updated(self, row: ModuleRow, branch: str, _result: dict[str, Any]) -> None:
        row.branch_button.setEnabled(True)
        row.set_branch(branch)
        service_name = pick(row.module, "name", "module_name", default="当前服务")
        self.show_success("修改成功", f"{service_name} 分支已更新为：{branch}")

    def build_pack_payload(self) -> dict[str, Any]:
        need_apollo = bool(self.apollo_edit.text().strip())
        modules = [
            payload
            for row in self.module_rows
            if (payload := row.selected_payload(need_apollo)) is not None
        ]
        return {
            "offline": 1 if self.offline_radio.isChecked() else 0,
            "support_cpu": self.cpu_combo.currentText(),
            "seafile": self.seafile_switch.isChecked(),
            "namespace": self.namespace_edit.text().strip() or "basic-app",
            "platform": [],
            "support_os": [],
            "modules": modules,
        }

    def submit_pack(self) -> None:
        if not self.current_version:
            self.show_error("无法打包", "请先选择一个版本。")
            return

        payload = self.build_pack_payload()
        if not payload["modules"]:
            self.show_error("无法打包", "请至少勾选一个业务组件。")
            return

        version_id = object_id(self.current_version)
        self.pack_button.setEnabled(False)
        self.pack_button.setText("正在提交...")
        self.run_task(
            lambda: self.api.submit_pack(version_id, payload),
            self._on_pack_submitted,
            "提交打包失败",
        )

    def _on_pack_submitted(self, result: dict[str, Any]) -> None:
        self.pack_button.setEnabled(True)
        self.pack_button.setText("开始打包")
        message = pick(result, "msg", "message", "detail", default="打包任务已提交。")
        self.show_success("提交成功", message)


class LoginConfigInterface(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("loginConfigInterface")
        self.credential_store = CredentialStore()

        saved = self.credential_store.load()

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(16)

        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)
        header.addWidget(SubtitleLabel("登录配置"))
        desc = BodyLabel("配置默认登录账号密码，保存后下次启动登录页会自动填入。")
        desc.setObjectName("MutedLabel")
        header.addWidget(desc)

        card = CardWidget()
        card_layout = QGridLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setHorizontalSpacing(16)
        card_layout.setVerticalSpacing(14)

        self.username_edit = LineEdit()
        self.username_edit.setClearButtonEnabled(True)
        self.username_edit.setText(str(saved.get("username") or CredentialStore.DEFAULT_USERNAME))

        self.password_edit = PasswordLineEdit()
        self.password_edit.setClearButtonEnabled(True)
        self.password_edit.setText(str(saved.get("password") or CredentialStore.DEFAULT_PASSWORD))

        self.remember_checkbox = CheckBox("登录页默认记住账号密码")
        self.remember_checkbox.setChecked(bool(saved.get("remember", True)))

        self.reset_button = PushButton("恢复默认")
        self.reset_button.setIcon(FIF.RETURN)
        self.reset_button.clicked.connect(self.reset_defaults)

        self.save_button = PrimaryPushButton("保存配置")
        self.save_button.setIcon(FIF.SAVE)
        self.save_button.clicked.connect(self.save_config)

        card_layout.addWidget(BodyLabel("默认账号"), 0, 0)
        card_layout.addWidget(self.username_edit, 0, 1)
        card_layout.addWidget(BodyLabel("默认密码"), 1, 0)
        card_layout.addWidget(self.password_edit, 1, 1)
        card_layout.addWidget(self.remember_checkbox, 2, 1)

        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(self.reset_button)
        action_row.addWidget(self.save_button)
        card_layout.addLayout(action_row, 3, 0, 1, 2)

        root.addLayout(header)
        root.addWidget(card)
        root.addStretch()

    def reset_defaults(self) -> None:
        self.username_edit.setText(CredentialStore.DEFAULT_USERNAME)
        self.password_edit.setText(CredentialStore.DEFAULT_PASSWORD)
        self.remember_checkbox.setChecked(True)

    def save_config(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username or not password:
            self.show_error("保存失败", "默认账号和密码不能为空。")
            return
        self.credential_store.save(username, password, self.remember_checkbox.isChecked())
        self.show_success("保存成功", "默认登录账号密码已更新。")

    def show_success(self, title: str, content: str) -> None:
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000,
            parent=self.window(),
        )

    def show_error(self, title: str, content: str) -> None:
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=5000,
            parent=self.window(),
        )


class MainWindow(FluentWindow):
    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        setTheme(Theme.LIGHT)
        self.setWindowTitle("项目打包桌面客户端")
        self.resize(1480, 900)
        self.setMinimumSize(1220, 760)

        self.packing_interface = PackingInterface(api_client, self)
        self.login_config_interface = LoginConfigInterface(self)
        self.addSubInterface(
            self.packing_interface,
            FIF.APPLICATION,
            "项目打包",
            position=NavigationItemPosition.TOP,
        )
        self.addSubInterface(
            self.login_config_interface,
            FIF.SETTING,
            "登录配置",
            position=NavigationItemPosition.BOTTOM,
        )
        self.navigationInterface.setExpandWidth(180)

        self.setStyleSheet(
            """
            PackingInterface {
                background: #f6f8fb;
            }
            LoginConfigInterface {
                background: #f6f8fb;
            }
            CardWidget {
                border-radius: 16px;
            }
            #MutedLabel {
                color: #64748b;
            }
            #ProjectRow, #VersionRow, #ModuleRow {
                background: transparent;
                border-radius: 10px;
            }
            #FormCard, #ModuleCard {
                background: rgba(255, 255, 255, 0.78);
            }
            QSplitter::handle {
                background: transparent;
            }
            """
        )
