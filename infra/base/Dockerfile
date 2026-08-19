# Образ-прихожая: в нём нет ничего, кроме способа войти.
#
# Всё тяжёлое — python, CUDA, torch, веса — ставится при старте, потому что
# docker качает ровно три слоя одновременно и по одному потоку на слой, а
# ghcr режет каждое соединение до ~25 Мбит/с.  Три потока = 76 Мбит/с, и это
# потолок независимо от канала машины (у неё бывает 1500) и от того, как
# разложены слои.  Шесть гигабайт через docker ехали 10.7 минуты; те же
# байты мимо docker, в тридцать соединений, едут около минуты.
#
# Поэтому здесь остаётся только то, что нельзя доставить иначе: sshd.  Без
# него vast не пускает внутрь (свой демон он в чужой образ не кладёт), а
# значит и распаковать доставленное будет некому.
FROM debian:12-slim

RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      openssh-server \
      rsync \
      zstd \
      curl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /run/sshd /root/.ssh \
 && chmod 700 /root/.ssh \
 && sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' \
      /etc/ssh/sshd_config \
 && sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' \
      /etc/ssh/sshd_config

# uv ставит и сам python, и всё остальное — так в образе не нужен даже python.
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    HF_HUB_ENABLE_HF_TRANSFER=0

# vast подменяет команду своей, но для запуска вручную пусть будет осмысленная.
CMD ["/usr/sbin/sshd", "-D", "-e"]
