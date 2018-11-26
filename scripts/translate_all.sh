#!/usr/bin/env bash
for lang in 'es' 'it' 'fr' 'de' 'ja' 'zh-cn' 'ko'
do
  echo $lang
  find ../aframe/imports/screens/ |
    grep 'aframe-Bootstrap Linux KVM with Panorama.json' |
    sed 's/.*/"&"/' |
    xargs -n 1 -I{} python ./translate_aframe.py {} $lang

done

