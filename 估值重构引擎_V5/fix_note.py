import re

with open(r"D:\长流水前端\src\pages\AgentAvatar.tsx", "r", encoding="utf-8") as f:
    content = f.read()

# Find and replace the entire 修者注 panel
old_start = content.find('<div style={{ padding:\'14px 20px\',borderBottom:\'1px solid #2A2A2A\'')
if old_start < 0:
    old_start = content.find('<div style={{ padding:\'14px 20px\',borderBottom:"1px solid #2A2A2A"')
if old_start < 0:
    print("Could not find note panel start")
    exit(1)

# Find the matching closing tag for this div
# Count div depth from old_start
depth = 0
i = old_start
while i < len(content):
    if content[i:i+4] == '<div':
        depth += 1
        i += 4
    elif content[i:i+6] == '</div>':
        depth -= 1
        if depth == 0:
            old_end = i + 6
            break
        i += 6
    else:
        i += 1

old_block = content[old_start:old_end]
print(f"Old block: {len(old_block)} chars from {old_start} to {old_end}")

new_block = """<div onClick={()=>setNoteExpanded(!noteExpanded)} style={{ cursor:'pointer',padding:'12px 20px',borderBottom:'1px solid #2A2A2A',background:noteOn?'linear-gradient(90deg,rgba(173,255,0,.14) 0%,rgba(173,255,0,.05) 50%,transparent 100%)':'rgba(255,255,255,.01)',transition:'all .4s',position:'relative',overflow:'hidden' }}>
            <div className="note-array-bg" style={{ backgroundImage:'url("data:image/svg+xml,%3Csvg width=%2740%27 height=%2740%27 xmlns=%27http://www.w3.org/2000/svg%27%3E%3Cpath d=%27M20 2L38 20L20 38L2 20Z%27 fill=%27none%27 stroke=%27%23ADFF00%27 stroke-width=%270.3%27/%3E%3C/svg%3E")',opacity:noteOn?.25:.06 }}/>
            <div style={{ position:'absolute',inset:0,pointerEvents:'none',opacity:noteOn?.15:.04,transition:'opacity .4s',background:'radial-gradient(ellipse at 15% 50%,rgba(173,255,0,.4) 0%,transparent 70%)' }}/>
            {!noteOn&&<>{[10,50,85].map((left,i)=><span key={i} className="note-particle" style={{ left:`${left}%`,bottom:`${(i+1)*15}%`,fontSize:8+i*3,color:'#ADFF00',animationDelay:`${i*0.8}s` }}>◆</span>)}</>}
            <div style={{ display:'flex',alignItems:'center',gap:12,position:'relative',zIndex:1 }}>
              <span style={{ fontFamily:'serif',fontSize:22,color:noteOn?'#ADFF00':'#444',transition:'all .4s',textShadow:noteOn?'0 0 16px rgba(173,255,0,.6),0 0 32px rgba(173,255,0,.3)':'0 0 4px rgba(173,255,0,.15)',filter:noteOn?'brightness(1.3)':'grayscale(0.5)' }}>◇</span>
              <span style={{ fontFamily:"'Space Mono',monospace",fontSize:15,fontWeight:700,color:noteOn?'#ADFF00':'#666',letterSpacing:'0.16em',textShadow:noteOn?'0 0 8px rgba(173,255,0,.3)':'0 0 3px rgba(173,255,0,.1)',transition:'all .3s' }}>修 者 注</span>
              <button onClick={e=>{e.stopPropagation();setNoteOn(!noteOn);}} style={{ fontFamily:"'Space Mono',monospace",fontSize:13,fontWeight:700,padding:'5px 16px',borderRadius:6,border:'2px solid '+(noteOn?'#ADFF00':'rgba(173,255,0,.15)'),background:noteOn?'rgba(173,255,0,.12)':'rgba(173,255,0,.03)',color:noteOn?'#ADFF00':'#777',cursor:'pointer',letterSpacing:'0.1em',textShadow:noteOn?'0 0 12px rgba(173,255,0,.5)':'0 0 3px rgba(173,255,0,.12)',boxShadow:noteOn?'0 0 16px rgba(173,255,0,.2),inset 0 0 8px rgba(173,255,0,.1)':'0 0 4px rgba(173,255,0,.05)',transition:'all .3s',animation:noteOn?'pulse 2s ease-in-out infinite':'none' }}
                onMouseEnter={e=>{if(!noteOn){e.currentTarget.style.borderColor='#ADFF0080';e.currentTarget.style.color='#ADFF00';}}}
                onMouseLeave={e=>{if(!noteOn){e.currentTarget.style.borderColor='rgba(173,255,0,.15)';e.currentTarget.style.color='#777';}}}>{noteOn?'◇ 已采纳':'◇ 采纳'}</button>
              <span style={{ flex:1 }}/>
              <span style={{ fontFamily:"'Space Mono',monospace",fontSize:11,color:noteOn?'#ADFF00':'#555' }}>{cultivatorNote?`${cultivatorNote.length}字`:'空'}</span>
              <span style={{ fontFamily:"'Space Mono',monospace",fontSize:10,color:noteOn?'#ADFF00':'#444',transition:'transform .3s',transform:noteExpanded?'rotate(180deg)':'rotate(0deg)' }}>▼</span>
            </div>
            {noteExpanded&&<div style={{ position:'relative',zIndex:1,marginTop:12 }} onClick={e=>e.stopPropagation()}><textarea value={cultivatorNote} onChange={e=>setCultivatorNote(e.target.value)} rows={6} placeholder="独有资讯、另类数据、个人见解…" style={{ width:'100%',background:'rgba(0,0,0,.3)',border:'1px solid '+(noteOn?'rgba(173,255,0,.3)':'#333'),color:noteOn?'#DDD':'#888',fontFamily:"'IBM Plex Mono','Noto Sans SC',monospace",fontSize:14,padding:'12px 16px',outline:'none',borderRadius:6,resize:'vertical',lineHeight:1.8,transition:'all .3s' }}
            onFocus={e=>{e.currentTarget.style.borderColor='rgba(173,255,0,.6)';e.currentTarget.style.boxShadow='0 0 16px rgba(173,255,0,.2)';}}
            onBlur={e=>{e.currentTarget.style.borderColor=noteOn?'rgba(173,255,0,.3)':'#333';e.currentTarget.style.boxShadow='none';}}/></div>}
            </div>"""

content = content[:old_start] + new_block + content[old_end:]

with open(r"D:\长流水前端\src\pages\AgentAvatar.tsx", "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
