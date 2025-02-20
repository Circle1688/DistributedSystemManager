import asyncio
import configparser
import json
import subprocess

import psutil
import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTreeWidget, QTreeWidgetItem,
                             QPushButton, QVBoxLayout, QWidget, QHBoxLayout,
                             QInputDialog, QMessageBox, QMenu, QStatusBar)
from PyQt6.QtWebSockets import QWebSocket
from PyQt6.QtCore import QUrl, Qt, QTimer, pyqtSignal, QObject, QThread

PORT = 8888


# 工作线程类，用于执行 HTTP 请求
class RequestThread(QThread):
    # 定义一个信号，用于将请求结果传递回主线程
    result_signal = pyqtSignal(str)

    def run(self):
        url = "http://127.0.0.1:8010/get_all_queue_tasks"  # 示例 URL
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                pending_tasks_count = data['pending_tasks_count']
                started_tasks_count = data['started_tasks_count']
                self.result_signal.emit(f"Pending: {pending_tasks_count} tasks   Processing: {started_tasks_count} tasks")
            else:
                self.result_signal.emit(f"Request failed: {response.status_code}")
        except requests.exceptions.RequestException as e:
            self.result_signal.emit(f"Task server offline")


class NodeSignal(QObject):
    update_status = pyqtSignal(str, str)
    update_program_status = pyqtSignal(list, str)


class NodeManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.nodes = []
        self.server_process = None
        self.server_path = ""
        self.load_config()

        self.tree = QTreeWidget()
        self.signals = NodeSignal()
        self.initUI()
        self.loadNodes()
        self.setupSignals()

    def initUI(self):
        self.setWindowTitle("Distributed System Manager")
        self.setGeometry(100, 100, 800, 600)
        widget = QWidget()
        layout = QVBoxLayout()

        # 按钮布局
        buttonLayout = QHBoxLayout()
        self.runServerBtn = QPushButton("Run server")
        self.stopServerBtn = QPushButton("Stop server")
        self.addBtn = QPushButton("Add node")
        self.delBtn = QPushButton("Delete node")
        self.startAllBtn = QPushButton("Start all nodes")
        self.stopAllBtn = QPushButton("Stop all nodes")
        self.status_bar = QStatusBar()

        serverbuttonLayout = QHBoxLayout()

        buttonLayout.addWidget(self.addBtn)
        buttonLayout.addWidget(self.delBtn)
        buttonLayout.addWidget(self.startAllBtn)
        buttonLayout.addWidget(self.stopAllBtn)

        serverbuttonLayout.addWidget(self.runServerBtn)
        serverbuttonLayout.addWidget(self.stopServerBtn)

        # 树形列表
        self.tree.setHeaderLabels(["IP address", "status"])
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.showContextMenu)

        layout.addLayout(serverbuttonLayout)
        layout.addLayout(buttonLayout)
        layout.addWidget(self.tree)
        self.setStatusBar(self.status_bar)
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        # 按钮事件绑定
        self.runServerBtn.clicked.connect(self.start_server)
        self.stopServerBtn.clicked.connect(self.stop_server)

        self.addBtn.clicked.connect(self.addNode)
        self.delBtn.clicked.connect(self.deleteNode)
        self.startAllBtn.clicked.connect(self.startAllPrograms)
        self.stopAllBtn.clicked.connect(self.stopAllPrograms)

        # 创建定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.start_request)
        self.timer.start(2000)  # 每隔2秒触发一次

        # 创建定时器
        self.json_timer = QTimer()
        self.json_timer.timeout.connect(self.export_tree_to_json)
        self.json_timer.start(2000)  # 每隔2秒触发一次


    def load_config(self):
        config = configparser.ConfigParser()
        config.read("config.ini")
        if "default" in config:
            self.server_path = config["default"]["server"]

    def export_tree_to_json(self):
        def get_item_data(item, is_root=True):
            """
            递归获取 QTreeWidgetItem 的数据
            """
            if is_root:
                # 根节点使用 IP 和 Status
                item_data = {
                    "IP": item.text(0),
                    "status": item.text(1)
                }
            else:
                # 子节点使用 Process 和 Status
                item_data = {
                    "process": item.text(0),
                    "status": item.text(1)
                }

            children = []
            for i in range(item.childCount()):
                child = item.child(i)
                children.append(get_item_data(child, is_root=False))  # 子节点递归调用时 is_root=False
            if children:
                item_data["process"] = children
            return item_data

        root_data = []
        for i in range(self.tree.topLevelItemCount()):
            root_item = self.tree.topLevelItem(i)
            root_data.append(get_item_data(root_item))

        with open('status.json', "w") as f:
            json.dump(root_data, f, indent=4)

    def start_server(self):
        self.server_process = subprocess.Popen(
            self.server_path,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )

    def stop_server(self):
        if self.server_process:
            process = psutil.Process(self.server_process.pid)
            children = process.children(recursive=True)
            for child in children:
                try:
                    child.terminate()  # 发送终止信号
                except psutil.NoSuchProcess:
                    print(f"Process {child.pid} no longer exist.")
            process.terminate()
            print(f"server exit.")
            self.server_process = None

    def start_request(self):
        # 创建并启动工作线程
        self.thread = RequestThread()
        self.thread.result_signal.connect(self.update_status_bar)
        self.thread.start()

    def update_status_bar(self, message):
        # 更新状态栏
        self.status_bar.showMessage(message)

    def setupSignals(self):
        self.signals.update_status.connect(self.handleStatusUpdate)
        self.signals.update_program_status.connect(self.handleProgramStatusUpdate)

    def addNode(self):
        ip, ok = QInputDialog.getText(self, "Add node", "Enter the node IP address:")
        if ok:
            self.connectToNode(ip)

    def connectToNode(self, ip):
        for node in self.nodes:
            if node["ip"] == ip:
                QMessageBox.warning(self, "Warning", "This node already exists!!")
                return

        ws = QWebSocket()
        node_item = QTreeWidgetItem([f"{ip}", "connect..."])
        self.tree.addTopLevelItem(node_item)
        node = {
            "ip": ip,
            "ws": ws,
            "item": node_item,
            "programs": {}
        }
        self.nodes.append(node)
        ws.connected.connect(lambda: self.onConnected(ws))
        ws.disconnected.connect(lambda: self.onDisconnected(ws))
        ws.textMessageReceived.connect(lambda msg: self.onMessageReceived(ws, msg))
        ws.open(QUrl(f"ws://{ip}:{PORT}"))
        self.saveNodes()


    def connect_to_server(self, ws, ip):
        ws.open(QUrl(f"ws://{ip}:{PORT}"))

    def onConnected(self, ws):
        for node in self.nodes:
            if node["ws"] == ws:
                node["item"].setText(1, "online")
                ws.sendTextMessage(json.dumps({"type": "get_programs"}))

    def onDisconnected(self, ws):
        for node in self.nodes:
            if node["ws"] == ws:
                node["item"].setText(1, "offline")
                for child in list(node["programs"].values()):
                    node["item"].removeChild(child["item"])
                node["programs"].clear()

        # for node in self.nodes:
        #     if node["ws"] == ws:
        #         ip = node["ip"]
        #         break

        # ws.open(QUrl(f"ws://{ip}:{PORT}"))

    def onMessageReceived(self, ws, message):
        try:
            data = json.loads(message)
            if data["type"] == "programs":
                for node in self.nodes:
                    if node["ws"] == ws:
                        for program in data["programs"]:
                            program_item = QTreeWidgetItem([program["name"], program["status"]])
                            node["item"].addChild(program_item)
                            node["programs"][program["name"]] = {
                                "item": program_item,
                                "status": program["status"]
                            }
                        node["item"].setExpanded(True)
            elif data["type"] == "status_update":
                self.signals.update_program_status.emit(
                    data["programs"],
                    ws.peerAddress().toString()
                )
        except Exception as e:
            print("Error processing message:", e)

    def handleStatusUpdate(self, ip_port, status):
        for node in self.nodes:
            if f"{node['ip']}:{PORT}" == ip_port:
                node["item"].setText(1, status)

    def handleProgramStatusUpdate(self, programs, ip):
        for prog in programs:
            program_name = prog['name']
            status = prog['status']
            for node in self.nodes:
                if node['ip'] == ip:
                    if program_name in node["programs"]:
                        node["programs"][program_name]["item"].setText(1, status)
                        node["programs"][program_name]["status"] = status

    def deleteNode(self):
        selected = self.tree.selectedItems()
        if not selected:
            return

        item = selected[0]
        for node in self.nodes:
            if node["item"] == item:
                node["ws"].close()
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
                self.nodes.remove(node)
                self.saveNodes()
                break

    def showContextMenu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            return

        if item.parent() is None:
            menu = QMenu()
            start_action = menu.addAction("Start all programs")
            stop_action = menu.addAction("Stop all programs")

            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            if action == start_action:
                self.controlAllProgramsOneNode(item, "start")
            elif action == stop_action:
                self.controlAllProgramsOneNode(item, "stop")
            return

        menu = QMenu()
        start_action = menu.addAction("Start")
        stop_action = menu.addAction("Stop")

        action = menu.exec(self.tree.viewport().mapToGlobal(position))
        if action == start_action:
            self.controlProgram(item, "start")
        elif action == stop_action:
            self.controlProgram(item, "stop")


    def controlProgram(self, item, action):
        program_name = item.text(0)
        parent = item.parent()
        for node in self.nodes:
            if node["item"] == parent:
                msg = {"type": action, "program": program_name}
                node["ws"].sendTextMessage(json.dumps(msg))
                break


    def controlAllProgramsOneNode(self, item, action):
        ip = item.text(0)
        for node in self.nodes:
            if node["ip"] == ip:
                node["ws"].sendTextMessage(json.dumps({"type": f"{action}_all"}))


    def startAllPrograms(self):
        for node in self.nodes:
            node["ws"].sendTextMessage(json.dumps({"type": "start_all"}))

    def stopAllPrograms(self):
        for node in self.nodes:
            # if node["ws"].state() == QWebSocket.State.ConnectedState:
            node["ws"].sendTextMessage(json.dumps({"type": "stop_all"}))

    def saveNodes(self):
        data = [{"ip": node["ip"]} for node in self.nodes]
        with open("nodes.json", "w") as f:
            json.dump(data, f)

    def loadNodes(self):
        try:
            with open("nodes.json", "r") as f:
                data = json.load(f)
                for node in data:
                    self.connectToNode(node["ip"])
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    app = QApplication([])
    window = NodeManager()
    window.show()
    app.exec()