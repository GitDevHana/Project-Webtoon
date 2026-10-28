"""Reusable native SVG comic balloon contours; no generated raster assets."""
def shape_svg(kind,w,h,anchor=.5):
 w=float(w);h=float(h);a=max(.26,min(.74,float(anchor)));x=w*a;b=max(15,min(30,w*.03));dx=-22 if a<.4 else 22 if a>.6 else 8
 if kind in ('narration','inner_narration'):
  return f'<rect class="narration-box" x="2" y="2" width="{w-4}" height="{h-4}" fill="#fffefa" stroke="#40392f" stroke-width="2.5"/>'
 if kind=='speech':
  # One closed contour: curved body flows into a tapered, curved tail.
  d=(f'M {w*.20} 9 C {w*.36} 1 {w*.66} 0 {w*.80} 10 '
     f'C {w*.94} 17 {w-7} {h*.17} {w-7} {h*.43} '
     f'C {w-5} {h*.76} {w*.94} {h*.94} {w*.81} {h-9} '
     f'C {w*.75} {h+1} {x+b+16} {h-4} {x+b} {h-5} '
     f'Q {x+b-6} {h+13} {x+dx} {h+37} '
     f'Q {x-3} {h+14} {x-b} {h-6} '
     f'C {x-b-16} {h-3} {w*.19} {h+1} {w*.10} {h*.93} '
     f'C {w*.02} {h*.83} 7 {h*.67} 7 {h*.45} '
     f'C 6 {h*.19} {w*.07} 16 {w*.20} 9 Z')
  return f'<path class="balloon-outline speech-contour" d="{d}" fill="white" stroke="#40392f" stroke-width="3" stroke-linejoin="round"/>'
 if kind=='thought':
  # Same soft cloud family already used by the episode editor.
  d=(f'M {w*.16} {h*.06} C {w*.04} {-h*.01} {-w*.03} {h*.28} {w*.04} {h*.43} '
     f'C {-w*.02} {h*.67} {w*.07} {h*.94} {w*.22} {h*.92} '
     f'C {w*.37} {h*1.03} {w*.62} {h*1.03} {w*.75} {h*.93} '
     f'C {w*.97} {h*.99} {w*1.03} {h*.7} {w*.97} {h*.51} '
     f'C {w*1.04} {h*.23} {w*.87} {-h*.02} {w*.73} {h*.06} '
     f'C {w*.58} {-h*.03} {w*.31} {-h*.03} {w*.16} {h*.06} Z')
  return (f'<path class="balloon-outline thought-contour" d="{d}" fill="white" stroke="#40392f" stroke-width="3"/>'
          f'<ellipse cx="{x}" cy="{h+12}" rx="12" ry="9" fill="white" stroke="#40392f" stroke-width="2.5"/>'
          f'<ellipse cx="{x+dx}" cy="{h+32}" rx="6" ry="4" fill="white" stroke="#40392f" stroke-width="2"/>')
 return ''
