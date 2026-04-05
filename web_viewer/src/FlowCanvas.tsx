import { useEffect, useState } from 'react';
import {
  ReactFlow,
  Controls,
  ReactFlowProvider,
  useReactFlow
} from '@xyflow/react';
import type {
  NodeProps,
  Node
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

function SvgNode({ data }: NodeProps) {
  return (
    <div 
      style={{ 
        background: '#fff',
        pointerEvents: 'none' // Клики проходят сквозь, работает только зум и панорамирование
      }}
      dangerouslySetInnerHTML={{ __html: data.svg as string }}
    />
  );
}

const nodeTypes = {
  svgViewer: SvgNode,
};

interface FlowCanvasProps {
  svgString: string;
  title: string;
}

function FlowCanvasInner({ svgString, title }: FlowCanvasProps) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const { fitView } = useReactFlow();

  useEffect(() => {
    // Делаем один огромный узел по центру
    const initialNodes: Node[] = [
      {
        id: '1',
        type: 'svgViewer',
        data: { svg: svgString },
        position: { x: 0, y: 0 },
        draggable: true, 
      }
    ];
    setNodes(initialNodes);
    
    setTimeout(() => {
      fitView({ duration: 0, padding: 0.1 });
    }, 50);
  }, [svgString, fitView]);

  return (
    <div className="app-container" style={{ width: '100%', height: '100%', background: '#fff' }}>
      <div className="header" style={{ position: 'absolute', top: 15, left: 15, zIndex: 10 }}>
        <h3 style={{ margin: 0, background: 'rgba(255,255,255,0.8)', padding: '5px 10px', borderRadius: '4px' }}>
          Функция: {title}
        </h3>
      </div>
      <div className="flow-wrapper" style={{ width: '100%', height: '100%' }}>
        <ReactFlow
          nodes={nodes}
          edges={[]}
          nodeTypes={nodeTypes}
          minZoom={0.05} 
          style={{ background: '#fff' }} // Чисто белый фон, без Background (точечек)
        >
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}

export function FlowCanvas(props: FlowCanvasProps) {
  return (
    <ReactFlowProvider>
       <FlowCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
