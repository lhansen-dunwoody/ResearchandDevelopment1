import json
import os
import socket

HOST = os.environ.get("RD01_HOST", "192.168.181.128")
PORT = int(os.environ.get("RD01_PORT", "8080"))
MAX_MESSAGE_BYTES = 16384

HELP = """Commands:
  whoami             Show the lab client's account and computer name
  hostname           Show the lab client's computer name
  pwd                Show the current lab directory
  ls / dir           List the current lab directory
  cd <directory>     Move within the client's starting lab directory
  checkUserLevel     Check whether the client is running elevated
  help               Show available commands
  terminate          Disconnect and exit
"""


def send_message(stream, message):
    payload = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError("Message too large")
    stream.write(payload)
    stream.flush()


def receive_message(stream):
    raw = stream.readline(MAX_MESSAGE_BYTES + 1)
    if not raw:
        raise ConnectionError("Client disconnected")
    if len(raw) > MAX_MESSAGE_BYTES or not raw.endswith(b"\n"):
        raise ValueError("Invalid or oversized message")
    message = json.loads(raw)
    if not isinstance(message, dict) or not isinstance(message.get("output"), str):
        raise ValueError("Unexpected response format")
    return message


def main():
    print("=" * 60)
    print("RESEARCH AND DEVELOPMENT 01 | ISOLATED TCP LAB")
    print("=" * 60)
    print(HELP)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)
        print(f"[+] Listening for incoming TCP connections on {HOST}:{PORT}")
        with server.accept()[0] as connection:
            print("[+] Lab client connected")
            # Independent read/write file objects make each request/response
            # unambiguous, unlike recv(5000) in the original Week 6 scripts.
            with connection.makefile("rb") as reader, connection.makefile("wb") as writer:
                while True:
                    try:
                        command = input("Shell> ").strip()
                    except (EOFError, KeyboardInterrupt):
                        command = "terminate"
                        print()

                    if not command:
                        continue
                    if command == "help":
                        print(HELP)
                        continue
                    try:
                        send_message(writer, {"command": command})
                        if command == "terminate":
                            print("[+] Session ended")
                            break
                        result = receive_message(reader)
                        print(result["output"])
                    except (ConnectionError, OSError, ValueError, json.JSONDecodeError) as exc:
                        print(f"[-] Connection error: {exc}")
                        break


if __name__ == "__main__":
    main()
