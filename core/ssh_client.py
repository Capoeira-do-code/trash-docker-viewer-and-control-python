# core/ssh_client.py
import paramiko

class SSHClient:
    def __init__(self, host, user, password=None, key_path=None, port=22):
        self.host = host
        self.user = user
        self.password = password
        self.key_path = key_path
        self.port = port
        self.client = None

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if self.key_path:
            pkey = paramiko.RSAKey.from_private_key_file(self.key_path)
            self.client.connect(self.host, port=self.port, username=self.user, pkey=pkey)
        else:
            self.client.connect(self.host, port=self.port, username=self.user, password=self.password)

    def exec_command(self, command):
        if not self.client:
            raise Exception("SSH client not connected")
        stdin, stdout, stderr = self.client.exec_command(command)
        return stdout

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
