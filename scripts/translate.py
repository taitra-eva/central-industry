"""Offline translation of RSS titles and meaningful publisher-provided excerpts.
No paid API, no guessed summaries, and no copied copyrighted full articles.
Failure to download/install language models leaves original text unchanged.
"""
import json
import re
from html import unescape
from pathlib import Path
from topic_taxonomy import normalize_article

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/news.json"

def language(text):
    """Detect content language; Chinese originals override unreliable RSS hints.

    Latin currency symbols, acronyms and numbers in Chinese headlines must not
    trigger English translation. Japanese kana takes precedence over kanji.
    """
    if re.search(r"[\u3040-\u30ff]", text or ""):
        return "ja"
    if len(re.findall(r"[\u4e00-\u9fff]", text or ""))>=2:
        return None
    if re.search(r"[A-Za-z]", text or ""):
        return "en"
    return None

def title_language(article):
    title=article.get("title","")
    detected=language(title)
    if detected is None and len(re.findall(r"[\u4e00-\u9fff]",title))>=2:
        return None
    return detected or article.get("language_hint")

def main():
    import argostranslate.package
    import argostranslate.translate
    from opencc import OpenCC
    converter = OpenCC("s2twp")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    entries = data.get("items", [])
    # Repair old records created when an erroneous "en" hint caused
    # already-Chinese headlines to be translated again.
    for article in entries:
        title=article.get("title","")
        if len(re.findall(r"[\u4e00-\u9fff]",title))>=2 and not re.search(r"[\u3040-\u30ff]",title):
            if article.get("translation_method")=="argos_offline_machine_translation":
                article.pop("title_zh",None)
                article.pop("translation_method",None)
            if article.get("language_hint") in ("en","zh"):
                article.pop("language_hint",None)
    raw_file = ROOT / ".article_texts.json"
    source_texts = json.loads(raw_file.read_text(encoding="utf-8")) if raw_file.exists() else {}
    needed = set()
    for x in entries:
        if not x.get("title_zh") and (lang := title_language(x)):
            needed.add(lang)
        if x.get("excerpt") and not x.get("excerpt_translation_zh") and (lang := language(x["excerpt"])):
            needed.add(lang)
    if not needed and not source_texts:
        print("No foreign items or source bodies to translate")
        return
    installed = {(p.from_code,p.to_code) for p in argostranslate.package.get_installed_packages()}
    if source_texts:
        needed.update(language(body[:250]) for body in source_texts.values() if language(body[:250]))
    required = {("en","zh")} if "en" in needed or "ja" in needed else set()
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
        src = title_language(x)
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
        body = source_texts.get(x.get("id"), "")
        if len(body) >= 250 and not x.get("summary_zh"):
            # Faithful source excerpts, NOT a generative AI summary.
            paragraphs=[p.strip() for p in re.split(r"\n+", body) if len(p.strip()) > 55]
            chosen=[]
            total=0
            for para in paragraphs:
                if total + len(para) > 1900: break
                chosen.append(para)
                total += len(para)
                if len(chosen) >= 8: break
            selected="\n\n".join(chosen)
            lang=language(selected[:300])
            if selected and lang in ("en","ja"):
                try:
                    translated=translate_to_zh(selected,lang)
                    if translated and translated.strip():
                        x["summary_zh"]=converter.convert(translated.strip())[:950]
                        x["summary_status"]="source_excerpt_translated"
                except Exception as ex:
                    print("Source passage translation failed:",str(ex)[:120])
            elif selected and not lang:
                x["summary_zh"]=selected[:600]
                x["summary_status"]="source_excerpt_translated"
    for x in entries: normalize_article(x)
    DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    untranslated=[x for x in entries if not x.get("title_zh") and title_language(x)]
    print("Translated titles:",count,"total:",len(entries),"foreign titles still missing Chinese:",len(untranslated))
    for x in untranslated[:10]: print("MISSING TITLE TRANSLATION:",x.get("region"),x.get("title","")[:100])

if __name__=="__main__":
    main()
