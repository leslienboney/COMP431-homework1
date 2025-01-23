import re
import os
import shutil
import sys


def parse_ftp_input_user_command(ftp_input_data):
    """
    Parses FTP input to extract the username from the USER command (case-insensitive).

    Args:
        ftp_input_data (str): The raw FTP input string.

    Returns:
        str: Extracted username if the USER command is valid, else an error message.
    """
    user_command_pattern = r'^(USER)\s+([a-zA-Z0-9_.-]+)\r\n$'

    match = re.match(user_command_pattern, ftp_input_data, re.IGNORECASE)

    if match:
        return "331 Guest access OK, send password.\r\n"
    return "501 Syntax error in parameter.\r\n"


def handle_pass_command(ftp_input_data, user_authenticated):
    """
    Handles and checks syntax of PASS command.

    Args:
        ftp_input_data (str): FTP input
        user_authenticated (bool): True iff valid USER command has been received.

    Returns:
        str: Response of success or failure and reason for failure.
    """
    if not user_authenticated:
        return "503 Bad sequence of commands.\r\n"

    pass_command_pattern = r'^(PASS)\s+([^\r\n]+)\r\n$'
    match = re.match(pass_command_pattern, ftp_input_data, re.IGNORECASE)

    if match:
        return "230 Guest login OK.\r\n"
    return "501 Syntax error in parameter.\r\n"


def handle_syst_command():
    """
    Handles SYST command and returns system type.

    Returns:
        str: Reply with UNIX system type.
    """
    return "215 UNIX Type: L8.\r\n"


def handle_port_command(ftp_input_data):
    """
    Handles and checks format of PORT command.

    Args:
        ftp_input_data (str): FTP input.

    Returns:
        tuple: IP address, port, and response message.
    """
    port_command_pattern = r'^(PORT)\s+(\d{1,3}),(\d{1,3}),(\d{1,3}),(\d{1,3}),(\d{1,3}),(\d{1,3})\r\n$'
    match = re.match(port_command_pattern, ftp_input_data, re.IGNORECASE)

    if match:
        ip_address = ".".join(match.group(i) for i in range(2, 6))  # First four groups are the IP
        port = (int(match.group(6)) << 8) + int(match.group(7))  # Last two groups are the port
        return ip_address, port, "200 Port command successful.\r\n"
    return None, None, "501 Syntax error in parameter.\r\n"


def handle_retr_command(ftp_input_data, retr_counter, port_set):
    """
    Handles the RETR command and retrieves the requested file.

    Args:
        ftp_input_data (str): FTP input for RETR command.
        retr_counter (int): Counter for naming retrieved files sequentially.
        port_set (bool): Indicates if a valid PORT command has been received.

    Returns:
        tuple: Updated retr_counter and response message.
    """
    if not port_set:
        return retr_counter, "503 Bad sequence of commands. Use PORT before RETR.\r\n"

    retr_command_pattern = r'^(RETR)\s+([^\r\n]+)\r\n$'
    match = re.match(retr_command_pattern, ftp_input_data, re.IGNORECASE)

    if match:
        file_path = match.group(2)
        if os.path.exists(file_path):
            dest_dir = "retr_files"
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            retr_counter += 1
            dest_file = os.path.join(dest_dir, f"file{retr_counter}")
            shutil.copy(file_path, dest_file)
            return retr_counter, "150 File status okay.\r\n250 Requested file action completed.\r\n"
        return retr_counter, "550 Requested action not taken. File unavailable.\r\n"
    return retr_counter, "501 Syntax error in parameter.\r\n"


def handle_type_command(ftp_input_data):
    """
    Handles and checks TYPE command.

    Args:
        ftp_input_data (str): FTP input.

    Returns:
        str: Returns type set or error and explanation.
    """
    type_command_pattern = r'^(TYPE)\s+([A-Z])\r\n$'
    match = re.match(type_command_pattern, ftp_input_data, re.IGNORECASE)

    if match and match.group(2) == "I":
        return "200 Type set to I.\r\n"
    return "501 Syntax error in parameter.\r\n"


def handle_noop_command():
    """
    Handles NOOP and tells client the server is running.

    Returns:
        str: Response indicating the server is okay.
    """
    return "200 Command okay.\r\n"


def handle_quit_command():
    """
    Terminates session.

    Returns:
        str: Response indicating the session is terminated.
    """
    return "200 Command OK.\r\n"


def handle_ftp_command(command, user_authenticated, retr_counter, port_set):
    """
    Determines responses to FTP commands.

    Args:
        command (str): Input FTP command.
        user_authenticated (bool): True iff valid USER command has been received.
        retr_counter (int): Counter for naming retrieved files.
        port_set (bool): Indicates if a valid PORT command has been received.

    Returns:
        tuple: Updated user_authenticated, retr_counter, port_set, and response.
    """
    command_upper = command.upper()

    if command_upper.startswith("USER"):
        parts = command.strip().split()
        if len(parts) < 2:
            sys.stdout.write("> USER\n")
            return user_authenticated, retr_counter, port_set, "501 Syntax error in parameter.\r\n"
        sys.stdout.write(f"> USER {parts[1]}\n")
        response = parse_ftp_input_user_command(command.strip() + "\r\n")
        if "331" in response:
            user_authenticated = True
        return user_authenticated, retr_counter, port_set, response
    elif command_upper.startswith("PASS"):
        parts = command.strip().split()
        if len(parts) < 2:
            sys.stdout.write("> PASS\n")
            return user_authenticated, retr_counter, port_set, "501 Syntax error in parameter.\r\n"
        sys.stdout.write(f"> PASS {parts[1]}\n")
        response = handle_pass_command(command.strip() + "\r\n", user_authenticated)
        return user_authenticated, retr_counter, port_set, response
    elif command_upper.startswith("SYST"):
        sys.stdout.write("> SYST\n")
        return user_authenticated, retr_counter, port_set, handle_syst_command()
    elif command_upper.startswith("TYPE"):
        parts = command.strip().split()
        if len(parts) < 2:
            sys.stdout.write("> TYPE\n")
            return user_authenticated, retr_counter, port_set, "501 Syntax error in parameter.\r\n"
        sys.stdout.write(f"> TYPE {parts[1]}\n")
        return user_authenticated, retr_counter, port_set, handle_type_command(command.strip() + "\r\n")
    elif command_upper.startswith("PORT"):
        parts = command.strip().split()
        if len(parts) < 2:
            sys.stdout.write("> PORT\n")
            return user_authenticated, retr_counter, port_set, "501 Syntax error in parameter.\r\n"
        sys.stdout.write(f"> PORT {parts[1]}\n")
        ip, port, response = handle_port_command(command.strip() + "\r\n")
        if "200" in response:
            port_set = True
        return user_authenticated, retr_counter, port_set, response
    elif command_upper.startswith("RETR"):
        parts = command.strip().split()
        if len(parts) < 2:
            sys.stdout.write("> RETR\n")
            return user_authenticated, retr_counter, port_set, "501 Syntax error in parameter.\r\n"
        sys.stdout.write(f"> RETR {parts[1]}\n")
        retr_counter, response = handle_retr_command(command.strip() + "\r\n", retr_counter, port_set)
        return user_authenticated, retr_counter, port_set, response
    elif command_upper.startswith("QUIT"):
        sys.stdout.write("> QUIT\n")
        return user_authenticated, retr_counter, port_set, handle_quit_command()
    elif command_upper.startswith("NOOP"):
        sys.stdout.write("> NOOP\n")
        return user_authenticated, retr_counter, port_set, handle_noop_command()
    else:
        sys.stdout.write(f"> {command_upper}\n")
        return user_authenticated, retr_counter, port_set, "500 Syntax error, command unrecognized.\r\n"

# Main loop
user_authenticated = False
retr_counter = 0
port_set = False

while True:
    sys.stdout.write("Enter FTP command: ")
    command = input().strip()
    user_authenticated, retr_counter, port_set, response = handle_ftp_command(
        command, user_authenticated, retr_counter, port_set
    )
    sys.stdout.write(response)
    if command.upper().startswith("QUIT"):
        break