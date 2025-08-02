import asyncio

import websockets
import json
import os
from time import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Access variables using os.getenv()
SAFETY_KEY = os.getenv('SAFETY_KEY')
if SAFETY_KEY is None:
    print("NO SAFETY KEY IN .env ALERT ALERT BAD BAD SET IT NOW")
    exit(1)

os.makedirs('./working/', exist_ok=True)

mem_db: [int, dict] = {}


# saving function
def save_mem_db():
    for i in range(1, 401):
        if 'dirty' not in mem_db[i]:
            continue
        mem_db[i].pop('dirty')
        with open(f"./working/task{i:03d}/data-{int(time()):010d}.json", 'w') as f:
            json.dump(mem_db[i], fp=f)
    print(f"mem db saved at {time()}")


# function to save periodically
async def periodic_save():
    while True:
        save_mem_db()
        await asyncio.sleep(30)  # every 30s save to disk


async def send_messages(websocket):
    while True:
        await asyncio.sleep(0.02)
        if websocket.task is None:
            continue
        print(mem_db)
        msg = {
            'timing': time(),
            'solution': mem_db[websocket.task]['solution'],
            'annotations': mem_db[websocket.task]['annotations']
        }
        await websocket.send(json.dumps(msg))


async def receive_messages(websocket):
    try:
        async for msg_text in websocket:

            msg = json.loads(msg_text)

            if ('safety_key' not in msg) or (not isinstance(msg['safety_key'], str)):
                await websocket.send(json.dumps({"type": "error", "error_msg": "data has to have string 'safety_key'"}))
                continue

            if msg['safety_key'] != SAFETY_KEY:
                await websocket.send(json.dumps({"type": "error", "error_msg": "lol no"}))
                continue

            if ('type' not in msg) or (not isinstance(msg['type'], str)):
                await websocket.send(json.dumps({"type": "error", "error_msg": "data has to have string 'type'"}))
                continue

            # listen on a task solution or annotation updates
            if msg['type'] == 'set-listen':

                if ('task' not in msg) or (not isinstance(msg['task'], int)):
                    await websocket.send(json.dumps({"type": "error", "error_msg": "data has to have integer 'task'"}))
                    continue
                task = msg['task']

                websocket.task = task

            # update the solution or annotation for a task
            elif msg['type'] == "update":

                if ('task' not in msg) or (not isinstance(msg['task'], int)):
                    await websocket.send(json.dumps({"type": "error", "error_msg": "data has to have integer 'task'"}))
                    continue
                task = msg['task']

                if task != websocket.task:
                    await websocket.send(
                        json.dumps({"type": "error", "error_msg": "cant update task that you are not viewing for safety"}))
                    continue

                if ('timing' not in msg) or (not isinstance(msg['timing'], float)):
                    await websocket.send(
                        json.dumps({"type": "error", "error_msg": "data has to have integer 'timing'"}))
                    continue

                if abs(msg['timing']-time()) > 2.0:  # max latency
                    await websocket.send(
                        json.dumps({"type": "error", "error_msg": "excessive latency, update denied"}))
                    continue

                has_solution = ('solution' in msg) and (isinstance(msg['solution'], str))
                has_annotations = ('annotations' in msg) and (isinstance(msg['annotations'], str))
                if not (has_annotations or has_solution):
                    await websocket.send(
                        json.dumps({"type": "error", "error_msg": "requires either 'annotation' or 'solution'"}))
                    continue

                if has_solution and has_annotations:  # to prevent potential issues
                    await websocket.send(json.dumps({"type": "error", "error_msg": "thats sus ...."}))
                    continue

                if has_solution:
                    mem_db[task]['solution'] = msg['solution']

                if has_annotations:
                    mem_db[task]['annotations'] = msg['annotations']

                mem_db[task]['dirty'] = True
            else:
                await websocket.send(json.dumps({"type": "error", "error_msg": f"unknown type of '{msg['type']}'"}))
                continue
    except websockets.exceptions.ConnectionClosedOK:
        print("Connection closed by peer.")
    except json.JSONDecodeError as e:
        print("JSON Decode error", e)
    finally:
        save_mem_db()


async def conn(websocket):
    websocket.task = None

    send_task = asyncio.create_task(send_messages(websocket))
    receive_task = asyncio.create_task(receive_messages(websocket))

    # Wait for both tasks to complete (or for some other termination condition)
    await asyncio.gather(send_task, receive_task)


DEFAULT_TASK_DATA = {
    "solution": "",
    "annotations": ""
}


async def main():
    for i in range(1, 401):
        # write defaults
        os.makedirs(f"./working/task{i:03d}", exist_ok=True)
        if not os.path.isfile(f"./working/task{i:03d}/data.json"):
            with open(f"./working/task{i:03d}/data-0000000000.json", 'w') as f:
                json.dump(DEFAULT_TASK_DATA, fp=f)

        # load from latest file
        with open(f"./working/task{i:03d}/{[*sorted(os.listdir(f'./working/task{i:03d}/'))][-1]}", 'r') as f:
            mem_db[i] = json.load(f)

    # periodic saving
    asyncio.ensure_future(periodic_save())

    # noinspection PyTypeChecker
    async with websockets.serve(conn, "0.0.0.0", 6969):
        print("WebSocket server started on ws://0.0.0.0:6969")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
