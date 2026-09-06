# The hallway image: nothing in it but delivery tools.
#
# Everything heavy -- python, CUDA, torch, weights -- is installed at start-up,
# because docker pulls exactly three layers at once and one stream per layer,
# while ghcr throttles every connection to ~25 Mbit/s.  Three streams = 76
# Mbit/s, and that is the ceiling whatever the machine's channel (it can be
# 1500) and however the layers are arranged.  Six gigabytes travelled through
# docker in 10.7 minutes; the same bytes past docker, over thirty connections,
# travel in about a minute.
#
# ssh is deliberately absent here.  vast builds its own ssh layer on top of any
# image and puts the keys there itself; an sshd of our own gets in the way of
# that build -- the daemon that comes up is ours, while the keys land in a
# foreign authorized_keys, and logging in gives "Permission denied
# (publickey)".  Checked.
FROM debian:12-slim

# rsync is needed by the result transport, zstd by unpacking what is
# delivered.  Installed here rather than in onstart: apt over the network at
# every start is the same half-minute we are trying to save.
#
# libgl1 and libglib2.0-0 -- for opencv, which paddlex pulls in behind it: the
# cv2 wheel links against the system libGL, and without it importing paddleocr
# falls with "ImportError: libGL.so.1". In the former Ubuntu image they came
# along with CUDA; in clean Debian they are absent.
# libgomp1 -- OpenMP, numpy and paddle link against it.
# gcc, g++ and libc6-dev -- for triton and flashinfer: both compile kernels on
# the fly.  gcc alone is not enough, the kernels are C++: nvcc calls the host
# compiler and falls with "cannot execute cc1plus".
#
# procps -- for `pgrep`/`pkill`, and that is no convenience. `run.sh` searches
# for and finishes off vLLM orphans with them; they were not in the image, and
# both lines returned code 127 SILENTLY. Two troubles at once: "no foreign vLLM
# processes on the machine" was printed ALWAYS, regardless of the fact -- a
# speaking zero, forbidden by the project rule -- and the sweep rested on a
# single `kill -- -$SRV`, while the neighbouring comment says outright why a
# second line of defence was added: "EngineCore holds no port socket and
# outlived the parent". An orphan on 60% of the video memory is the very
# trouble `--served-model-name` and the model-name check were written for.
# Checked by taking both layers of the image apart: `procps`, `psmisc`,
# `iproute2` are not installed, `pgrep`, `pkill`, `ps`, `fuser`, `ss` absent.
#
# AND THAT IS STILL TRUE OF THE IMAGE ACTUALLY RENTED. `procps` and `git` were
# added to THIS file in `ed4cb11`, while `models/paddleocr_vl/__init__.py`
# still names `vast-base:d69de6e`, built from the eleven-package version. The
# lines below take effect only once the image is rebuilt and `BASE_IMAGE`
# moves to the new tag; until then `run.sh`'s pgrep guard is not a second line
# of defence but the only one.
#
# git -- for one line of the snapshot. `stamp.commit()` asks git in the package
# directory; on the box there is none, and the paid run -- the one everything
# was written for -- turned out the only one without a record of which code
# counted it. The knob `BOOKSMITH_COMMIT` closes that without git as well, but
# let git be here too: 20 MB.
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      rsync \
      zstd \
      curl \
      ca-certificates \
      libgl1 \
      libglib2.0-0 \
      libgomp1 \
      gcc \
      g++ \
      libc6-dev \
      procps \
      git \
 && rm -rf /var/lib/apt/lists/*

# vast itself installs openssh into the built image and puts the key there --
# but puts it as a file writable by everyone, and sshd rejects such an
# authorized_keys: "bad ownership or modes for file
# /root/.ssh/authorized_keys", that is Permission denied (publickey) with a
# correct key.  In vast's own images something compensates for this; in clean
# Debian nothing does.
#
# We switch the mode check off instead of chasing the modes: the machine is
# rented for one task, there are no other users on it, and the repair must
# work regardless of when exactly vast writes the file.
RUN mkdir -p /etc/ssh/sshd_config.d \
 && printf 'StrictModes no\n' > /etc/ssh/sshd_config.d/10-vast-keys.conf

# uv installs python itself as well as all the wheels -- so the image needs no
# python of its own.
#
# The version is pinned and must match the one that built constraints.txt.
# Otherwise this happens: the list is built by uv 0.12.5 and installed by uv
# 0.9.7, which does not yet know about torchcodec in the pytorch index -- and
# the run falls with "no version of torchcodec==0.16.0+cu130", though the
# wheel is there in the index.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=180
