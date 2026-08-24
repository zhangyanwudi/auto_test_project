from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticfilesRunserverCommand,
)

from base_utils.terminal_utils import terminal_hyperlink


class Command(StaticfilesRunserverCommand):
    """开发服务器：默认监听 0.0.0.0，启动时输出局域网 IP 访问地址。"""

    default_addr = '0.0.0.0'

    def on_bind(self, server_port):
        super().on_bind(server_port)
        local_ip = getattr(settings, 'LOCAL_IP', None)
        if not local_ip:
            return
        lan_url = f'http://{local_ip}:{server_port}/'
        local_url = f'http://127.0.0.1:{server_port}/'
        self.stdout.write(
            self.style.SUCCESS(
                f'\n局域网访问: {terminal_hyperlink(lan_url, lan_url, stream=self.stdout)}\n'
                f'本机访问:   {terminal_hyperlink(local_url, local_url, stream=self.stdout)}\n'
            )
        )
