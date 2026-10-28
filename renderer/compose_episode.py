"""Explicit artwork/lettering composition for new episodes. No auto-placement."""
from pathlib import Path
import argparse, base64, copy, json, math, subprocess, uuid
ROOT=Path(__file__).resolve().parents[1]

def rect(value, label, width, height):
    if not isinstance(value,list) or len(value)!=4 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in value):
        raise ValueError(label+": explicit [x,y,w,h] required")
    x,y,w,h=value
    if x<0 or y<0 or w<=0 or h<=0 or x+w>width+.1 or y+h>height+.1:
        raise ValueError(label+": outside scene")
    return value

def validate(board, draft=False):
    if board.get("lettering_contract")!=2: raise ValueError("lettering_contract=2 required; legacy auto-layout is not supported")
    typography=board.get("typography",{})
    if not typography.get("family"): raise ValueError("Choose the document font before composition")
    if not draft and not typography.get("font_file"): raise ValueError("Production requires an embeddable Korean font file; no system-font substitution")
    cuts=board.get("cuts",[])
    if not cuts: raise ValueError("No storyboard cuts")
    ids=set()
    for c in cuts:
        cid=c["cut_id"]
        if cid in ids: raise ValueError("Duplicate cut ID: "+cid)
        ids.add(cid)
        layout=c.get("composition",{})
        height=layout.get("height",0)
        if not isinstance(height,(int,float)) or not math.isfinite(height) or height<=0: raise ValueError(cid+": explicit scene height required")
        rect(layout.get("art_rect"),cid+" artwork",1080,height)
        if not layout.get("reason") or not layout.get("reading_flow"): raise ValueError(cid+": composition reason and reading flow required")
        if not isinstance(layout.get("gap"),(int,float)) or layout["gap"]<0: raise ValueError(cid+": explicit gap required")
        for i,t in enumerate(c.get("lettering",[])):
            if not isinstance(t.get("text"),str) or not t.get("text_kind"): raise ValueError(cid+": approved literal text and text_kind required")
            if "approved_text" in t and t["approved_text"]!=t["text"]: raise ValueError(cid+": text differs from approved source")
            l=t.get("layout",{})
            rect(l.get("rect"),cid+" lettering "+str(i),1080,height)
            if not isinstance(l.get("font_size"),(int,float)) or not 12<=l["font_size"]<=300: raise ValueError(cid+": explicit font_size required")
            if l.get("align") not in ["left","center","right"]: raise ValueError(cid+": explicit text alignment required")
            if t["text_kind"] in ["speech","thought"]:
                target=l.get("tail_target")
                if not isinstance(target,list) or len(target)!=2 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in target): raise ValueError(cid+": explicit speaker connector target required")
                if not (0<=target[0]<=1080 and 0<=target[1]<=height): raise ValueError(cid+": connector target outside scene")
                if l.get("tail_side") not in ["top","bottom","left","right"]: raise ValueError(cid+": connector side required")
    return board

def compose(board, episode_dir, draft=False):
    validate(board,draft)
    typography=board["typography"]
    episode=board.get("episode",board.get("webtoon_episode"))
    if isinstance(episode,int): episode=f"EP{episode:02d}"
    if not isinstance(episode,str) or not episode.startswith("EP"): raise ValueError("Explicit episode ID required")
    doc={"schemaVersion":"projectWT.editor/1","id":str(uuid.uuid4()),"episode":episode,"title":board.get("title",episode),"canvasWidth":1080,"letteringContract":2,"bakedText":False,"typography":{"family":typography["family"],"requireEmbeddedFont":not draft},"fonts":[],"assets":{},"panels":[],"deletedPanels":[],"projectContext":{"projectName":"projectWT"},"directives":{"localizedEdits":True,"preserveComposition":True,"sourceFidelity":True},"productionStatus":"layout_draft_not_final" if draft else "assembled_pending_visual_review"}
    if board.get("balloon_style"):
        doc["balloonStyle"]=board["balloon_style"]
    if typography.get("font_file"):
        font=(ROOT/typography["font_file"]).resolve()
        if not font.is_relative_to(ROOT) or not font.is_file(): raise ValueError("Font must be a project file")
        mime={".woff2":"font/woff2",".woff":"font/woff",".ttf":"font/ttf",".otf":"font/otf"}[font.suffix.lower()]
        doc["fonts"]=[{"family":typography["family"],"weight":typography.get("weight",400),"src":"data:"+mime+";base64,"+base64.b64encode(font.read_bytes()).decode()}]
    for c in board["cuts"]:
        cid=c["cut_id"];layout=c["composition"]
        asset=(episode_dir/c["art_asset"]).resolve()
        if not asset.is_relative_to(ROOT) or not asset.is_file(): raise ValueError(cid+": missing project artwork")
        mime={".png":"image/png",".webp":"image/webp",".jpg":"image/jpeg",".jpeg":"image/jpeg",".svg":"image/svg+xml"}[asset.suffix.lower()]
        aid=episode+"-"+cid
        doc["assets"][aid]={"id":aid,"src":"data:"+mime+";base64,"+base64.b64encode(asset.read_bytes()).decode()}
        x,y,w,h=layout["art_rect"]
        layers=[{"id":cid+"-art","type":"image","assetId":aid,"x":x,"y":y,"w":w,"h":h,"rotation":0,"opacity":1,"alt":c.get("narrative_function","")}]
        for i,t in enumerate(c.get("lettering",[])):
            l=t["layout"];x,y,w,h=l["rect"];kind=t["text_kind"]
            layer={"id":t.get("id",cid+"-letter-"+str(i+1)),"type":"balloon" if kind in ["speech","thought"] else "text","letteringVersion":2,"text_kind":kind,"text":t["text"],"speaker":t.get("speaker_or_thinker",""),"x":x,"y":y,"w":w,"h":h,"fontSize":l["font_size"],"fontFamily":typography["family"],"fontWeight":l.get("font_weight",400),"lineHeight":l.get("line_height",1.35),"padding":l.get("padding",[20,24,20,24]),"align":l["align"],"verticalAlign":l.get("vertical_align","center"),"shape":"thought" if kind=="thought" else "ellipse" if kind=="speech" else "box","box":kind in ["narration","inner_narration","system"],"color":l.get("color","#29251e"),"fill":l.get("fill","#ffffff"),"stroke":l.get("stroke","#35312d"),"strokeWidth":l.get("stroke_width",2.5),"rotation":l.get("rotation",0),"opacity":1,"autoFit":False}
            if "lines" in l:
                if "".join(l["lines"]).split()!=t["text"].split() and "".join("".join(l["lines"]).split())!="".join(t["text"].split()): raise ValueError(cid+": line breaks must preserve literal text")
                layer["render_lines"]=l["lines"];layer["lines_for"]=t["text"]
            if kind in ["speech","thought"]:
                tx,ty=l["tail_target"];layer["tail"]={"x":(tx-x)/w,"y":(ty-y)/h,"side":l["tail_side"]}
            layers.append(layer)
        doc["panels"].append({"id":cid,"originCutId":cid,"title":c.get("narrative_function",cid),"width":1080,"height":layout["height"],"gapAfter":layout["gap"],"background":layout.get("background","#ffffff"),"layers":layers,"source":copy.deepcopy(c),"redraw":False,"notes":""})
    doc["baseline"]={"originalPanelIds":[p["id"] for p in doc["panels"]],"panels":copy.deepcopy(doc["panels"]),"importedFrom":"explicit-composition-v2"}
    return doc

def main():
    a=argparse.ArgumentParser();a.add_argument("storyboard",type=Path);a.add_argument("--draft",action="store_true");a.add_argument("--check",action="store_true");args=a.parse_args()
    p=args.storyboard.resolve()
    if not p.is_relative_to(ROOT): raise ValueError("Storyboard must be within project")
    board=json.loads(p.read_text(encoding="utf-8-sig"));validate(board,args.draft)
    if args.check: print("Explicit composition contract valid (not a visual approval)");return
    doc=compose(board,p.parent,args.draft)
    runner="require(process.argv[1]);let d=JSON.parse(require('fs').readFileSync(0,'utf8'));WTCore.normalize(d);process.stdout.write(WTCore.exportReader(d));"
    result=subprocess.run(["node","-e",runner,str(ROOT/"editor/core.js")],input=json.dumps(doc,ensure_ascii=False),encoding="utf-8",capture_output=True)
    if result.returncode: raise ValueError(result.stderr)
    prefix=doc["episode"]+("_layout_draft" if args.draft else "")
    (p.parent/(prefix+"_edit.wtedit.json")).write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding="utf-8")
    (p.parent/(prefix+"_scroll.html")).write_text(result.stdout,encoding="utf-8")
    print("Saved editable composition:",prefix)
if __name__=="__main__":main()
