"""Small local 3D prop blockout. Not image reconstruction, people or rigging."""
from pathlib import Path
from .core import finite,digest


def box_prop(width,height,depth,output):
    values=[finite(v,n,.001) for v,n in zip((width,height,depth),('width','height','depth'))]
    if any(v>100 for v in values):raise ValueError('Blockout dimension cap 100 units')
    p=Path(output)
    if p.exists() or p.suffix.lower()!='.obj':raise ValueError('Fresh OBJ output path required')
    w,h,d=[v/2 for v in values];vertices=[(-w,-h,-d),(w,-h,-d),(w,h,-d),(-w,h,-d),(-w,-h,d),(w,-h,d),(w,h,d),(-w,h,d)]
    faces=[(1,4,3,2),(5,6,7,8),(1,2,6,5),(4,8,7,3),(1,5,8,4),(2,3,7,6)]
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# Procedural box prop blockout, not reconstructed geometry\n'+''.join('v %g %g %g\n'%v for v in vertices)+''.join('f '+' '.join(map(str,f))+'\n' for f in faces))
    return {'path':str(p.resolve()),'sha256':digest(p),'vertices':8,'faces':6,'status':'procedural_box_blockout_not_reference_reconstruction','paid_requests':0}
