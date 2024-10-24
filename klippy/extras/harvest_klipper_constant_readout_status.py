import socket, json
import time

CHECK_HEARTBEAT_INTERVAL = 0.5


class ConstantReadout:
    """This class checks for the printer status and manipulates the shutdown object accordingly"""

    def __init__(self):
        """init of object

        :param shutdown_object: the shutdown object shared across all threads
        :type shutdown_object: ?
        :param logger: The logger object used for logging
        :type logger: ?
        """
        self.printer_available_status = True
        self.printing_status = True

    def main(self):
        """Opens the klippy socket and in intervals sends messages to klipper, based on the responses
        set the respective flags in the shutdown object"""
        # Set the path for the Unix socket
        socket_path = "/home/pi/printer_data/comms/klippy.sock"

        # Create the Unix socket client
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(CHECK_HEARTBEAT_INTERVAL)
        try:
            # Connect to the server
            client.connect(socket_path)
            while True:
                try:
                    # self.logger.info("Heartbeat: sending messages")
                    self.messaging(client)
                    time.sleep(CHECK_HEARTBEAT_INTERVAL)
                except Exception as e:
                    print(f"Exception: {e}")
        finally:
            client.close()

    def decode_socket_answer(self, msg):
        """Decode the message retrieved from the socket

        :param msg: incoming message
        :type msg: ?
        :return: the dictionary contained in the incoming message
        :rtype: dict
        """
        decoded = msg.decode()
        # ignore the last character which corresponds to the encoded \x03
        decoded = decoded.strip()[:-1]
        decoded = json.loads(decoded)
        return decoded

    def messaging(self, client):
        """Send the messages defined in "messages" to the client and wait for the answers. Then,
        based on the answers, decide the flags for printer and printing status. Also, retrieve the current print job id which is
        used to store all the data related to the same print job with the same ID.

        :param client: the client to send the message to
        :type client: ?
        """
        messages = [
            '{"id": 123, "method": "objects/query", "params": {"objects": {"virtual_sdcard": null, "harvest_klipper":null}}}\x03',
        ]
        try:
            for i in messages:
                try:
                    # Send a message to the server
                    client.sendall(i.encode())
                    msg = client.recv(1024)
                    m = self.decode_socket_answer(msg)
                    result = m["result"]["status"]["harvest_klipper"]
                    # responses.append(self.decode_socket_answer(msg))
                    print(f"MESSAGE {result}")
                    with open("result.txt", "+a") as f:
                        f.write(f"{result}\n")
                except Exception as e:
                    print(f"Exception: {e}")

        except Exception as e:
            print(f"Exception: {e}")


if __name__ == "__main__":
    h = ConstantReadout()
    h.main()
