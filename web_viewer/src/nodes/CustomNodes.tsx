import { Handle, Position, NodeResizer } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';

// Невидимые стили для Handle (точек подключения)
const handleStyle = { opacity: 0, width: '100%', height: '100%', top: 0, left: 0, position: 'absolute' as any, zIndex: -1 };

export function TerminalNode({ data, selected }: NodeProps) {
  return (
    <div className="gost-node gost-terminal" style={{ minWidth: 120, height: 50, borderRadius: 25, border: '2px solid #333', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <NodeResizer color="#09f" isVisible={selected} minWidth={100} minHeight={40} />
      <Handle type="target" position={Position.Top} style={{...handleStyle, top: '0', height: '10%'}} />
      <div style={{ padding: '0 20px', textAlign: 'center' }}>{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} style={{...handleStyle, top: 'auto', bottom: '0', height: '10%'}} />
    </div>
  );
}

export function ProcessNode({ data, selected }: NodeProps) {
  return (
    <div className="gost-node gost-process" style={{ minWidth: 150, height: 60, border: '2px solid #333', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <NodeResizer color="#09f" isVisible={selected} minWidth={100} minHeight={40} />
      <Handle type="target" position={Position.Top} style={{...handleStyle, top: '0', height: '10%'}} />
      <div style={{ padding: '10px 15px', textAlign: 'center' }}>{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} style={{...handleStyle, top: 'auto', bottom: '0', height: '10%'}} />
    </div>
  );
}

export function ConditionNode({ data, selected }: NodeProps) {
  // Ромб можно сделать через clip-path
  return (
    <div style={{ position: 'relative', minWidth: 150, minHeight: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <NodeResizer color="#09f" isVisible={selected} minWidth={120} minHeight={80} />
      
      {/* Сам ромб (графика) */}
      <div style={{
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        background: '#fff',
        border: '2px solid #333',
        clipPath: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)',
        zIndex: 1
      }} />

      {/* Текст поверх ромба */}
      <div style={{ position: 'relative', zIndex: 2, padding: '10px 20px', textAlign: 'center', maxWidth: '70%' }}>
        {data.label as string}
      </div>

      <Handle type="target" position={Position.Top} style={{...handleStyle, top: '0', height: '10%', zIndex: 3}} />
      <Handle type="source" position={Position.Bottom} id="bottom" style={{...handleStyle, top: 'auto', bottom: '0', height: '10%', zIndex: 3}} />
      <Handle type="source" position={Position.Left} id="left" style={{...handleStyle, left: '0', width: '10%', zIndex: 3}} />
      <Handle type="source" position={Position.Right} id="right" style={{...handleStyle, left: 'auto', right: '0', width: '10%', zIndex: 3}} />
    </div>
  );
}

export function IONode({ data, selected }: NodeProps) {
  return (
    <div style={{ position: 'relative', minWidth: 160, minHeight: 60, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <NodeResizer color="#09f" isVisible={selected} minWidth={120} minHeight={50} />
      
      <div style={{
        position: 'absolute',
        top: 0, left: '10%', right: '10%', bottom: 0,
        background: '#fff',
        border: '2px solid #333',
        transform: 'skew(-15deg)',
        width: '80%',
        zIndex: 1
      }} />

      <div style={{ position: 'relative', zIndex: 2, padding: '10px 20px', textAlign: 'center' }}>
        {data.label as string}
      </div>

      <Handle type="target" position={Position.Top} style={{...handleStyle, top: '0', height: '10%', zIndex: 3}} />
      <Handle type="source" position={Position.Bottom} style={{...handleStyle, top: 'auto', bottom: '0', height: '10%', zIndex: 3}} />
    </div>
  );
}

export function PredefinedProcessNode({ data, selected }: NodeProps) {
  return (
    <div className="gost-predefined" style={{ minWidth: 150, minHeight: 60, border: '2px solid #333', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
      <NodeResizer color="#09f" isVisible={selected} minWidth={100} minHeight={40} />
      <div style={{ position: 'absolute', top: 0, bottom: 0, left: '10px', borderLeft: '2px solid #333' }} />
      <div style={{ position: 'absolute', top: 0, bottom: 0, right: '10px', borderRight: '2px solid #333' }} />
      
      <Handle type="target" position={Position.Top} style={{...handleStyle, top: '0', height: '10%'}} />
      <div style={{ padding: '10px 25px', textAlign: 'center', zIndex: 2 }}>{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} style={{...handleStyle, top: 'auto', bottom: '0', height: '10%'}} />
    </div>
  );
}
