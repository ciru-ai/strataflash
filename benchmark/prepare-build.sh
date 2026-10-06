#!/usr/bin/env bash
set -euo pipefail
TASK=/benchmark-storage
mkdir -p "$TASK"
cd "$TASK"
if [ ! -d source ]; then
  git clone --depth 1 --branch v0.1.40 https://github.com/Niko1221/Strata.git source
fi
test "$(git -C source rev-parse HEAD)" = 1735d6471df29b42c26170efaac1f1446a58640f
SDK="$TASK/rocm-7.14.1"
TARBALL="$TASK/therock-dist-linux-gfx1151-7.14.1.tar.gz"
if [ ! -f "$TASK/sdk-verified.json" ]; then
  curl -fL --retry 3 -C - https://repo.amd.com/rocm/tarball-multi-arch/therock-dist-linux-gfx1151-7.14.1.tar.gz -o "$TARBALL"
  printf '%s  %s\n' c40e8f2bd6630a7d11557c762b99c6fa8afb04c9bd0e51ed1675ee1ca24afb00 "$TARBALL" | sha256sum -c -
  mkdir -p "$SDK"
  tar -xzf "$TARBALL" -C "$SDK"
  test -f "$SDK/lib/llvm/bin/clang++"
  printf '{"sha256":"c40e8f2bd6630a7d11557c762b99c6fa8afb04c9bd0e51ed1675ee1ca24afb00","version":"7.14.1"}\n' > "$TASK/sdk-verified.json"
fi
export ROCM_PATH="$SDK" HIP_PATH="$SDK" HIP_PLATFORM=amd
export PATH="$SDK/bin:$SDK/lib/llvm/bin:$PATH"
export LD_LIBRARY_PATH="$SDK/lib:$SDK/lib/rocm_sysdeps/lib:$SDK/lib/llvm/lib:${LD_LIBRARY_PATH:-}"
GCC_LIBDIR=$(dirname "$(gcc -print-libgcc-file-name)")
GLIBC_HEADERS=$(g++ -E -x c++ -v /dev/null 2>&1 | sed -n 's/^ \(\/nix\/store\/.*-glibc-.*-dev\/include\)$/\1/p' | head -1)
GLIBC_LIBDIR=$(dirname "$(g++ -print-file-name=crt1.o)")
STDCXX_LIBDIR=$(dirname "$(g++ -print-file-name=libstdc++.so)")
cmake -S source -B build-halo -G Ninja -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_HIP_FLAGS_RELEASE=-O3 -DNDEBUG' \
  -DSTRATA_ENABLE_HIP=ON -DSTRATA_ENABLE_CUDA=OFF -DSTRATA_PREFILL_MMQ=ON \
  -DSTRATA_BUILD_TESTS=OFF -DCMAKE_HIP_ARCHITECTURES=gfx1151 \
  -DCMAKE_HIP_COMPILER="$SDK/lib/llvm/bin/clang++" -DCMAKE_HIP_COMPILER_ROCM_ROOT="$SDK" \
  "-DCMAKE_PREFIX_PATH=$SDK;$SDK/lib/rocm_sysdeps;$SDK/lib/llvm" \
  "-DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=$SDK/lib/llvm/bin/ld.lld -Wl,-m,elf_x86_64 -B$GLIBC_LIBDIR -L$GLIBC_LIBDIR -L$STDCXX_LIBDIR -Wl,-rpath,$GLIBC_LIBDIR -Wl,-rpath,$STDCXX_LIBDIR -Wl,--dynamic-linker=$GLIBC_LIBDIR/ld-linux-x86-64.so.2" \
  "-DCMAKE_HIP_FLAGS=--rocm-path=$SDK --rocm-device-lib-path=$SDK/lib/llvm/amdgcn/bitcode --gcc-install-dir=$GCC_LIBDIR -idirafter $GLIBC_HEADERS"
cmake --build build-halo --target strata -j8
sha256sum build-halo/strata > binary.sha256
printf '{"status":"BUILT","revision":"1735d6471df29b42c26170efaac1f1446a58640f","backend":"HIP","arch":"gfx1151","rocm":"7.14.1"}\n' > build-complete.json
