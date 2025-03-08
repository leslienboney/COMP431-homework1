import re
import sys
import os
import socket


class FTPServer:
    def __init__(self):
        self.session_state = {
            'authenticated': False,
            'expect_password': False,
            'data_channel': None,
            'transfer_mode': None,
            'client_address': None,
            'transfer_count': 0,
            'active_command': None
        }
        self.command_patterns = {
            'USER': re.compile(r'^\s*USER\s+([\x21-\x7E]+)\r\n$', re.I),
            'PASS': re.compile(r'^\s*PASS\s+([\x21-\x7E]*)\r\n$', re.I),
            'TYPE': re.compile(r'^TYPE\s+([AI])\r\n$', re.I),
            'RETR': re.compile(r'^RETR\s+(.+)\r\n$', re.I),
            'PORT': re.compile(r'^PORT\s+(\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\r\n$', re.I),
            'SYST': re.compile(r'^SYST\r\n$', re.I),
            'NOOP': re.compile(r'^NOOP\r\n$', re.I),
            'QUIT': re.compile(r'^QUIT\r\n$', re.I)
        }
        self.responses = {
            'welcome': "220 COMP 431 FTP server ready.\r\n",
            'auth_continue': "331 Guest access OK, send password.\r\n",
            'auth_success': "230 Guest login OK.\r\n",
            'quit': "221 Goodbye.\r\n",
            'syst_response': "215 UNIX Type: L8.\r\n",
            'noop_ok': "200 Command OK.\r\n",
            'type_ok': "200 Type set to {}.\r\n",
            'port_ok': "200 Port command successful ({},{}).\r\n",
            'transfer_start': "150 File status okay.\r\n",
            'transfer_success': "250 Requested file action completed.\r\n",
            'file_error': "550 File not found or access denied.\r\n",
            'sequence_error': "503 Bad sequence of commands.\r\n",
            'syntax_error': "500 Syntax error, command unrecognized.\r\n",
            'param_error': "501 Syntax error in parameter.\r\n",
            'access_denied': "530 Not logged in.\r\n",
            'data_fail': "425 Can not open data connection.\r\n"
        }
        self.setup_data_directory()

    def setup_data_directory(self):
        self.data_dir = "transferred_data"
        os.makedirs(self.data_dir, exist_ok=True)

    def process_command(self, input_line, connection):
        print(input_line, end='')

        if input_line.startswith(' '):
            return self.responses['syntax_error']

        cmd = input_line.split()[0].upper() if input_line else ''
        handler = getattr(self, f'handle_{cmd}', None)
        return handler(input_line, connection) if handler else self.responses['syntax_error']

    def handle_QUIT(self, *args):
        self.session_state['active_command'] = 'QUIT'
        return self.responses['quit']

    def handle_USER(self, cmd_line, *args):
        if match := self.command_patterns['USER'].match(cmd_line):
            self.session_state.update({
                'expect_password': True,
                'authenticated': False,
                'active_command': 'USER'
            })
            return self.responses['auth_continue']
        return self.responses['param_error']

    def handle_PASS(self, cmd_line, *args):
        if not self.session_state['expect_password']:
            return self.responses['sequence_error']

        if self.command_patterns['PASS'].match(cmd_line):
            self.session_state.update({
                'authenticated': True,
                'expect_password': False
            })
            return self.responses['auth_success']
        return self.responses['param_error']

    def handle_TYPE(self, cmd_line, *args):
        if match := self.command_patterns['TYPE'].match(cmd_line):
            return self.responses['type_ok'].format(match.group(1).upper())
        return self.responses['param_error']

    def handle_SYST(self, *args):
        return self.responses['syst_response']

    def handle_NOOP(self, *args):
        return self.responses['noop_ok']

    def handle_PORT(self, cmd_line, *args):
        if match := self.command_patterns['PORT'].match(cmd_line):
            ip = '.'.join(match.groups()[:4])
            port = int(match.group(5)) * 256 + int(match.group(6))
            self.session_state['client_address'] = (ip, port)
            return self.responses['port_ok'].format(ip, port)
        return self.responses['param_error']

    def handle_RETR(self, cmd_line, connection):
        if not self.session_state['authenticated']:
            return self.responses['access_denied']

        if not self.session_state['client_address']:
            return self.responses['sequence_error']

        if match := self.command_patterns['RETR'].match(cmd_line):
            filename = match.group(1)
            if not os.path.exists(filename):
                return self.responses['file_error']

            connection.sendall(self.responses['transfer_start'].encode())
            print(self.responses['transfer_start'], end='')

            try:
                data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data_sock.settimeout(10)
                data_sock.connect(self.session_state['client_address'])

                self.session_state['transfer_count'] += 1
                with open(filename, 'rb') as file:
                    while chunk := file.read(1024):
                        data_sock.sendall(chunk)

                data_sock.close()
                self.session_state['client_address'] = None
                return self.responses['transfer_success']
            except Exception:
                self.session_state['client_address'] = None
                return self.responses['data_fail']

        return self.responses['param_error']

    def start_server(self, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', port))
        sock.listen(5)

        while True:
            conn, addr = sock.accept()
            conn.sendall(self.responses['welcome'].encode())
            print(self.responses['welcome'], end='')

            self.session_state = {k: False if isinstance(v, bool) else None for k, v in self.session_state.items()}

            while True:
                try:
                    data = conn.recv(1024).decode()
                    if not data:
                        break

                    response = self.process_command(data, conn)
                    print(response, end='')
                    conn.sendall(response.encode())

                    if self.session_state.get('active_command') == 'QUIT':
                        break
                except:
                    break

            conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python server.py <PORT>")
        sys.exit(1)

    ftp = FTPServer()
    ftp.start_server(int(sys.argv[1]))