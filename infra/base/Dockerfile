# Образ-прихожая: в нём нет ничего, кроме инструментов доставки.
#
# Всё тяжёлое — python, CUDA, torch, веса — ставится при старте, потому что
# docker качает ровно три слоя одновременно и по одному потоку на слой, а
# ghcr режет каждое соединение до ~25 Мбит/с.  Три потока = 76 Мбит/с, и это
# потолок независимо от канала машины (у неё бывает 1500) и от того, как
# разложены слои.  Шесть гигабайт через docker ехали 10.7 минуты; те же
# байты мимо docker, в тридцать соединений, едут около минуты.
#
# ssh здесь намеренно нет.  vast достраивает любой образ своим слоем с ssh и
# сам кладёт туда ключи; собственный sshd этой достройке мешает — демон
# поднимается наш, а ключи попадают в чужой authorized_keys, и вход даёт
# "Permission denied (publickey)".  Проверено.
FROM debian:12-slim

# rsync нужен транспорту результатов, zstd — распаковке доставленного.
# Ставим здесь, а не в onstart: apt по сети при каждом старте — те же
# полминуты, которые мы и пытаемся сэкономить.
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      rsync \
      zstd \
      curl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# vast сам ставит в достроенный образ openssh и сам кладёт туда ключ — но
# кладёт его файлом, открытым на запись всем, и sshd такой authorized_keys
# отвергает: "bad ownership or modes for file /root/.ssh/authorized_keys",
# то есть Permission denied (publickey) при верном ключе.  В образах самого
# vast это чем-то компенсируется, в чистом Debian — нет.
#
# Снимаем проверку прав вместо того, чтобы гоняться за правами: машина
# арендована на одну задачу, других пользователей на ней нет, а починка
# должна работать независимо от того, когда именно vast запишет файл.
RUN mkdir -p /etc/ssh/sshd_config.d \
 && printf 'StrictModes no\n' > /etc/ssh/sshd_config.d/10-vast-keys.conf

# uv ставит и сам python, и все колёса — так в образе не нужен даже python.
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=180
