import asyncio
import websockets
import configparser
import json
import subprocess
import pygetwindow as gw
import psutil

PORT = 8888

class NodeServer:
    def __init__(self, host="0.0.0.0", port=PORT):
        self.host = host
        self.port = port
        self.programs = []
        self.processes = {}
        self.load_config()

    def load_config(self):
        config = configparser.ConfigParser()
        config.read("node_config.ini")
        if "programs" in config:
            self.programs = [
                {"name": name, "path": path}
                for name, path in config["programs"].items()
            ]

    async def start_program(self, name):
        for prog in self.programs:
            if prog["name"] == name:
                # 获取所有窗口
                windows = gw.getAllTitles()
                # 检查是否有窗口标题包含
                running = any(prog["name"] in title for title in windows)
                if running:
                    print(f"Process {name} already exist.")
                    return False
                try:
                    process = subprocess.Popen(
                        prog["path"],
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )
                    self.processes[name] = process
                    print(f"Start process {name} successful.")
                    return True
                except Exception as e:
                    print(f"Start process {name} failed:", e)
        return False

    async def stop_program(self, name):
        try:
            if name in self.processes:
                proc = self.processes[name]
                process = psutil.Process(proc.pid)
                children = process.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()  # 发送终止信号
                    except psutil.NoSuchProcess:
                        print(f"Process {child.pid} no longer exist.")
                process.terminate()
                print(f"Process {name} exit.")
                return True
            else:
                print(f"No permissions.The process {name} is not started by this node.")
                return False

        except Exception as e:
            print(f"Stop process error: {e}")
            return False

    async def get_status(self):
        # 获取所有窗口
        windows = gw.getAllTitles()

        status = []
        for prog in self.programs:
            # 检查是否有窗口标题包含
            running = any(prog["name"] in title for title in windows)
            status.append({
                "name": prog["name"],
                "status": "running" if running else "stopped"
            })
        return status

    async def handler(self, websocket):
        try:
            print("server connected")

            async for message in websocket:
                data = json.loads(message)
                if data["type"] == "get_programs":
                    status = await self.get_status()
                    await websocket.send(json.dumps({
                        "type": "programs",
                        "programs": status
                    }))
                elif data["type"] == "start":
                    success = await self.start_program(data["program"])
                    await asyncio.sleep(1)
                    status = await self.get_status()
                    await websocket.send(json.dumps({
                        "type": "status_update",
                        "programs": status
                    }))

                elif data["type"] == "stop":
                    success = await self.stop_program(data["program"])
                    await asyncio.sleep(1)
                    status = await self.get_status()
                    await websocket.send(json.dumps({
                        "type": "status_update",
                        "programs": status
                    }))

                elif data["type"] == "start_all":
                    for prog in self.programs:
                        await self.start_program(prog["name"])
                    await asyncio.sleep(1)
                    status = await self.get_status()
                    await websocket.send(json.dumps({
                        "type": "status_update",
                        "programs": status
                    }))
                elif data["type"] == "stop_all":
                    for name in list(self.processes.keys()):
                        await self.stop_program(name)
                    await asyncio.sleep(1)
                    status = await self.get_status()
                    await websocket.send(json.dumps({
                        "type": "status_update",
                        "programs": status
                    }))
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")

    async def run(self):
        async with websockets.serve(self.handler, self.host, self.port):
            await asyncio.Future()


if __name__ == "__main__":
    server = NodeServer()
    print(f"Node service starts in {server.host}:{server.port}")
    asyncio.run(server.run())
