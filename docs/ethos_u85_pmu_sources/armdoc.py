import sys,json,base64,re,html,urllib.request,os
def fetch(doc,ver,slug=""):
    u=f"https://documentation-service.arm.com/documentation/{doc}/{ver}"
    if slug: u+="/"+slug
    r=urllib.request.urlopen(u,timeout=60).read()
    return json.loads(r)
def text(d):
    c=d.get('content')
    if not c: return ""
    s=base64.b64decode(c).decode('utf8','replace')
    s=re.sub(r'<(script|style).*?</\1>','',s,flags=re.S)
    s=re.sub(r'</t[dh]>','\t',s); s=re.sub(r'</tr>','\n',s)
    s=re.sub(r'<[^>]+>','',s); s=html.unescape(s)
    return '\n'.join(l.strip() for l in s.split('\n') if l.strip())
def toc(doc,ver):
    d=fetch(doc,ver); rows=[]
    def w(n):
        rows.append((n.get('label'),n.get('slug')))
        for c in n.get('topics') or []: w(c)
    w(d['topic']); return rows
if __name__=="__main__":
    cmd=sys.argv[1]
    if cmd=="toc":
        for lab,slug in toc(sys.argv[2],sys.argv[3]): print(f"{lab}\t{slug}")
    else:
        print(text(fetch(sys.argv[2],sys.argv[3],sys.argv[4] if len(sys.argv)>4 else "")))
