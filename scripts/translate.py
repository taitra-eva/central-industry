"""Offline translation of RSS titles and meaningful publisher-provided excerpts.
No paid API, no guessed summaries, and no copied copyrighted full articles.
Failure to download/install language models leaves original text unchanged.
"""
import json
import re
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/news.json"

def language(text):
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[A-Za-z]", text) and not re.search(r"[\u4e00-\u9fff]", text):
        return "en"
    return None

def main():
    import argostranslate.package
    import argostranslate.translate
    from opencc import OpenCC
    converter = OpenCC("s2twp")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    entries = data.get("items", [])
    needed = set()
    for x in entries:
        if not x.get("title_zh") and (lang := language(x.get("title", ""))):
            needed.add(lang)
        if x.get("excerpt") and not x.get("excerpt_translation_zh") and (lang := language(x["excerpt"])):
            needed.add(lang)
    if not needed:
        print("No foreign items to translate")
        return
    installed = {(p.from_code,p.to_code) for p in argostranslate.package.get_installed_packages()}
    required = {("en","zh")} if needed else set()
    if "ja" in needed:
        required.add(("ja","en"))
    missing = required - installed
    if missing:
        try:
            argostranslate.package.update_package_index()
            available = argostranslate.package.get_available_packages()
            for src,dest in sorted(missing):
                package = next((p for p in available if p.from_code==src and p.to_code==dest),None)
                if not package:
                    print("No free offline package:",src,dest)
                    continue
                print("Installing offline model:",src,dest)
                argostranslate.package.install_from_path(package.download())
        except Exception as ex:
            print("Model download unavailable:", str(ex)[:180])
    langs = argostranslate.translate.get_installed_languages()
    bycode = {x.code:x for x in langs}
    count=0
    def translate_to_zh(text, src):
        if "zh" not in bycode or src not in bycode:
            return None
        if src=="ja":
            if "en" not in bycode:return None
            english=bycode["ja"].get_translation(bycode["en"]).translate(text)
            return bycode["en"].get_translation(bycode["zh"]).translate(english)
        return bycode[src].get_translation(bycode["zh"]).translate(text)
    for x in entries:
        original = x.get("title","")
        src = language(original)
        if src and not x.get("title_zh") and src in bycode and "zh" in bycode:
            try:
                translation=translate_to_zh(original,src)
                if translation and translation.strip()!=original.strip():
                    x["title_zh"]=converter.convert(translation.strip())
                    x["translation_method"]="argos_offline_machine_translation"
                    count+=1
            except Exception as ex:
                print("Translation error:",str(ex)[:100])
        excerpt = x.get("excerpt","")
        src = language(excerpt)
        if len(excerpt)>90 and src and not x.get("summary_zh") and src in bycode and "zh" in bycode:
            try:
                excerpt=unescape(re.sub("<[^>]+>"," ",excerpt))
                translation=translate_to_zh(excerpt[:1200],src)
                if translation and translation.strip()!=excerpt.strip():
                    x["excerpt_translation_zh"]=converter.convert(translation.strip())
                    x["excerpt_translation_status"]="machine_translation_of_source_excerpt"
            except Exception as ex:
                print("Excerpt translation error:",str(ex)[:100])
    DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Translated titles:",count, "total:",len(entries))

if __name__=="__main__":
    main()
