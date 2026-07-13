#!/usr/bin/env bash
# 產生迷你上游 fixtures(docs/AGENT_DEV.md §2.2)。產物提交進 git,已存在則跳過。
# - tiny-rpm:      2 個自製 rpm + createrepo_c repodata(rockylinux:9 容器內建置)
# - tiny-deb:      2 個自製 deb + dists/tiny 結構(debian:12-slim 容器內建置)
# - tiny-registry: FROM scratch 迷你 image push 進本地 registry:2 的 storage 目錄
set -euo pipefail
cd "$(dirname "$0")/.."
FIX="$PWD/fixtures"
HUID=$(id -u) HGID=$(id -g)

# ---------- tiny-rpm ----------
if [ -f "$FIX/tiny-rpm/repodata/repomd.xml" ]; then
  echo "OK: tiny-rpm 已存在,跳過"
else
  echo "== 建置 tiny-rpm =="
  mkdir -p "$FIX/tiny-rpm"
  docker run --rm -v "$FIX/tiny-rpm:/out" -e HUID="$HUID" -e HGID="$HGID" \
    docker.io/library/rockylinux:9 bash -euo pipefail -c '
      dnf -q install -y rpm-build createrepo_c >/dev/null
      mkdir -p /build/rpmbuild/{SPECS,RPMS}
      for name in tiny-hello tiny-bye; do
        cat > /build/rpmbuild/SPECS/$name.spec <<SPEC
Name:           $name
Version:        1.0
Release:        1
Summary:        Lab mirror test fixture package ($name)
License:        MIT
BuildArch:      noarch

%description
Tiny fixture package for lab-mirror dev tests. Contains one text file.

%install
mkdir -p %{buildroot}/usr/share/$name
echo "$name" > %{buildroot}/usr/share/$name/msg.txt

%files
/usr/share/$name/msg.txt
SPEC
        rpmbuild -bb --define "_topdir /build/rpmbuild" /build/rpmbuild/SPECS/$name.spec >/dev/null
      done
      mkdir -p /out/packages
      cp /build/rpmbuild/RPMS/noarch/*.rpm /out/packages/
      createrepo_c --quiet /out
      chown -R "$HUID:$HGID" /out
    '
  echo "OK: tiny-rpm 建置完成"
fi

# ---------- tiny-deb ----------
if [ -f "$FIX/tiny-deb/dists/tiny/Release" ]; then
  echo "OK: tiny-deb 已存在,跳過"
else
  echo "== 建置 tiny-deb =="
  mkdir -p "$FIX/tiny-deb"
  docker run --rm -v "$FIX/tiny-deb:/out" -e HUID="$HUID" -e HGID="$HGID" \
    docker.io/library/debian:12-slim bash -euo pipefail -c '
      apt-get update -qq >/dev/null
      apt-get install -y -qq --no-install-recommends dpkg-dev apt-utils gzip >/dev/null
      for name in tiny-hello-deb tiny-bye-deb; do
        d=/build/$name
        mkdir -p "$d/DEBIAN" "$d/usr/share/$name"
        echo "$name" > "$d/usr/share/$name/msg.txt"
        cat > "$d/DEBIAN/control" <<CTRL
Package: $name
Version: 1.0
Section: misc
Priority: optional
Architecture: amd64
Maintainer: lab-mirror fixtures <dev@lab.local>
Description: Lab mirror test fixture package ($name)
 Tiny fixture package for lab-mirror dev tests.
CTRL
        mkdir -p "/out/pool/main/t/$name"
        dpkg-deb --build --root-owner-group "$d" \
          "/out/pool/main/t/$name/${name}_1.0_amd64.deb" >/dev/null
      done
      cd /out
      mkdir -p dists/tiny/main/binary-amd64
      dpkg-scanpackages --arch amd64 pool > dists/tiny/main/binary-amd64/Packages
      gzip -k dists/tiny/main/binary-amd64/Packages
      apt-ftparchive \
        -o APT::FTPArchive::Release::Origin=lab-mirror-fixtures \
        -o APT::FTPArchive::Release::Suite=tiny \
        -o APT::FTPArchive::Release::Codename=tiny \
        -o APT::FTPArchive::Release::Components=main \
        -o APT::FTPArchive::Release::Architectures=amd64 \
        release dists/tiny > /tmp/Release
      mv /tmp/Release dists/tiny/Release
      chown -R "$HUID:$HGID" /out
    '
  echo "OK: tiny-deb 建置完成"
fi

# ---------- tiny-registry ----------
if [ -d "$FIX/tiny-registry/data/docker" ]; then
  echo "OK: tiny-registry 已存在,跳過"
else
  echo "== 建置 tiny-registry =="
  mkdir -p "$FIX/tiny-registry/data"
  ctx=$(mktemp -d)
  trap 'rm -rf "$ctx"; docker rm -f lab-mirror-fixreg >/dev/null 2>&1 || true' EXIT
  echo "hello from lab-mirror fixture" > "$ctx/hello.txt"
  cat > "$ctx/Dockerfile" <<'DF'
FROM scratch
COPY hello.txt /hello.txt
DF
  docker build --provenance=false -q -t localhost:5001/tiny/hello:1.0 "$ctx" >/dev/null
  docker tag localhost:5001/tiny/hello:1.0 localhost:5001/tiny/hello:latest
  docker run -d --name lab-mirror-fixreg -p 127.0.0.1:5001:5000 \
    -v "$FIX/tiny-registry/data:/var/lib/registry" docker.io/library/registry:2 >/dev/null
  for i in $(seq 1 20); do
    curl -sf http://localhost:5001/v2/ >/dev/null && break
    sleep 0.5
  done
  docker push -q localhost:5001/tiny/hello:1.0 >/dev/null
  docker push -q localhost:5001/tiny/hello:latest >/dev/null
  docker rm -f lab-mirror-fixreg >/dev/null
  # registry 以 root 寫入,交還 host 使用者以便 git 管理
  docker run --rm -v "$FIX/tiny-registry/data:/d" docker.io/library/rockylinux:9 \
    chown -R "$HUID:$HGID" /d
  echo "OK: tiny-registry 建置完成"
fi

echo "FIXTURES OK"
