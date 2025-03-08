import re
import sys
import os
import shutil
import socket


class FTPController:
    def __init__(self):
        self.session = {
            'authenticated': False,
            'expect_pass': False,
            'data_ready': False,
            'transfer_count': 0,
            'client_addr': None
        }
        self.command_patterns = {
            'USER': re.compile(r'^\s*USER\s+([^\r\n ][\x00-\x7F]*)\r\n$', re.I),
            'PASS': re.compile(r'^\s*PASS\s+([^\r\n ][\x00-\x7F]*)\r\n$', re.I),
            'TYPE': re.compile(r'^TYPE\s+([AI])\r\n$', re.I),
            'RETR': re.compile(r'^RETR\s+(.+)\r\n$', re.I),
            'PORT': re.compile(r'^PORT\s+(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\r\n$', re.I),
            'SYST': re.compile(r'^SYST\r\n$', re.I),
            'NOOP': re.compile(r'^NOOP\r\n$', re.I)
        }
        self.response_templates = {
            'welcome': "220 COMP 431 FTP server ready.\r\n",
            'auth_pending': "331 Guest access OK, send password.\r\n",
            'auth_success': "230 Guest login OK.\r\n",
            'quit': "221 Goodbye.\r\n",
            'syst': "215 UNIX Type: L8.\r\n",
            'noop': "200 Command OK.\r\n",
            'type': "200 Type set to {}.\r\n",
            'port_success': "200 Port command successful ({},{}).\r\n",
            'transfer_start': "150 File status okay.\r\n",
            'transfer_complete': "250 Requested file action completed.\r\n",
            'file_error': "550 File not found or access denied.\r\n",
            'sequence_error': "503 Bad sequence of commands.\r\n",
            'syntax_error': "500 Syntax error, command unrecognized.\r\n",
            'param_error': "501 Syntax error in parameter.\r\n",
            'access_denied': "530 Not logged in.\r\n",
            'conn_error': "425 Can not open data connection.\r\n"
        }
        self.output_dir = "retr_files"
        os.makedirs(self.output_dir, exist_ok=True)

    def validate_numbers(self, *values):
        return all(0 <= int(v) <= 255 for v in values)

    def process_input(self, command_str, connection):
        print(command_str, end='')

        if command_str[0].isspace():
            return self.response_templates['syntax_error']

        parts = command_str.strip().split(maxsplit=1)
        cmd_key = parts[0].upper() if parts else ""

        if cmd_key == "QUIT":
            return self.response_templates['quit']

        handler = getattr(self, f'handle_{cmd_key}', None)
        return handler(command_str, connection) if handler else self.response_templates['syntax_error']

    def handle_USER(self, cmd, _):
        if match := self.command_patterns['USER'].match(cmd):
            self.session.update({
                'expect_pass': True,
                'authenticated': False
            })
            return self.response_templates['auth_pending']
        return self.response_templates['param_error']

    def handle_PASS(self, cmd, _):
        if not self.session['expect_pass']:
            return self.response_templates['sequence_error']

        if self.command_patterns['PASS'].match(cmd):
            self.session.update({
                'authenticated': True,
                'expect_pass': False
            })
            return self.response_templates['auth_success']
        return self.response_templates['param_error']

    def handle_TYPE(self, cmd, _):
        if not self.session['authenticated']:
            return self.response_templates['access_denied']

        if match := self.command_patterns['TYPE'].match(cmd):
            return self.response_templates['type'].format(match[1].upper())
        return self.response_templates['param_error']

    def handle_SYST(self, cmd, _):
        return self.response_templates['syst'] if self.command_patterns['SYST'].match(cmd) else self.response_templates[
            'param_error']

    def handle_NOOP(self, cmd, _):
        return self.response_templates['noop'] if self.command_patterns['NOOP'].match(cmd) else self.response_templates[
            'param_error']

    def handle_PORT(self, cmd, _):
        if not self.session['authenticated']:
            return self.response_templates['access_denied']

        if match := self.command_patterns['PORT'].match(cmd):
            octets = match.groups()
            if self.validate_numbers(*octets):
                ip_addr = '.'.join(octets[:4])
                port_num = (int(octets[4]) << 8) + int(octets[5])
                self.session['client_addr'] = (ip_addr, port_num)
                self.session['data_ready'] = True
                return self.response_templates['port_success'].format(ip_addr, port_num)
        return self.response_templates['param_error']

    def handle_RETR(self, cmd, conn):
        if not self.session['authenticated']:
            return self.response_templates['access_denied']
        if not self.session['data_ready']:
            return self.response_templates['sequence_error']

        if match := self.command_patterns['RETR'].match(cmd):
            file_path = match[1]
            if not os.path.isfile(file_path):
                return self.response_templates['file_error']

            conn.sendall(self.response_templates['transfer_start'].encode())
            print(self.response_templates['transfer_start'], end='')

            try:
                with socket.socket() as data_sock:
                    data_sock.settimeout(10)
                    data_sock.connect(self.session['client_addr'])
                    with open(file_path, 'rb') as src_file:
                        while chunk := src_file.read(1024):
                            data_sock.sendall(chunk)

                self.session['transfer_count'] += 1
                dest_path = os.path.join(self.output_dir, f"file{self.session['transfer_count']}")
                shutil.copy(file_path, dest_path)
                return self.response_templates['transfer_complete']
            except Exception:
                return self.response_templates['conn_error']
            finally:
                self.session['data_ready'] = False
        return self.response_templates['param_error']

    def start_service(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as main_socket:
            main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            main_socket.bind(('', port))
            main_socket.listen(1)
            print(self.response_templates['welcome'], end='')

            while True:
                client, addr = main_socket.accept()
                with client:
                    client.send(self.response_templates['welcome'].encode())
                    self.session = {
                        'authenticated': False,
                        'expect_pass': False,
                        'data_ready': False,
                        'transfer_count': 0,
                        'client_addr': None
                    }

                    while True:
                        try:
                            data = client.recv(1024).decode()
                            if not data:
                                break
                            response = self.process_input(data, client)
                            print(response, end='')
                            client.send(response.encode())
                            if 'QUIT' in data.upper():
                                break
                        except Exception:
                            break


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 FTPserver.py <PORT>")
        sys.exit(1)
    FTPController().start_service(int(sys.argv[1]))