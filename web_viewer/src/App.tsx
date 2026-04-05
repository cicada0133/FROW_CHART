import { useState, useEffect } from 'react';
import { FlowCanvas } from './FlowCanvas';

interface FuncData {
  name: string;
  svg: string;
}

interface RenderSettings {
  max_width: number;
  horiz_spacing: number;
  vert_spacing: number;
  padding: number;
  font_size: number;
  return_wide_route: boolean;
  fill_blocks: boolean;
  staggered_switch: boolean;
}

const DEFAULT_SETTINGS: RenderSettings = {
  max_width: 200,
  horiz_spacing: 2,
  vert_spacing: 10,
  padding: 3,
  font_size: 79,
  return_wide_route: false,
  fill_blocks: true,
  staggered_switch: true
};

function App() {
  const [code, setCode] = useState('');
  const [funcs, setFuncs] = useState<FuncData[]>([]);
  const [activeFunc, setActiveFunc] = useState<FuncData | null>(null);
  const [loading, setLoading] = useState(false);

  // Глобальные настройки
  const [globalSettings, setGlobalSettings] = useState<RenderSettings>(DEFAULT_SETTINGS);
  
  // Локальные настройки (сохраненные для каждой функции отдельно)
  const [funcSettings, setFuncSettings] = useState<Record<string, RenderSettings>>({});
  
  // Текущие отображаемые настройки в панели
  const [currentPanelSettings, setCurrentPanelSettings] = useState<RenderSettings>(DEFAULT_SETTINGS);

  // Когда меняется активная функция, мы показываем ее локальные настройки (если есть) или глобальные
  useEffect(() => {
    if (activeFunc) {
        if (funcSettings[activeFunc.name]) {
            setCurrentPanelSettings(funcSettings[activeFunc.name]);
        } else {
            setCurrentPanelSettings(globalSettings);
        }
    }
  }, [activeFunc, funcSettings, globalSettings]);

  const handleParse = async (applyToAll: boolean) => {
    setLoading(true);
    
    let newGlobalSettings = globalSettings;
    let newFuncSettings = { ...funcSettings };

    if (applyToAll) {
        // Если применить ко всем: делаем текущие настройки панели глобальными, и сбрасываем локальные
        newGlobalSettings = currentPanelSettings;
        setGlobalSettings(newGlobalSettings);
        newFuncSettings = {};
        setFuncSettings({});
    } else if (activeFunc) {
        // Если только для текущей: сохраняем настройки панели только для активной функции
        newFuncSettings[activeFunc.name] = currentPanelSettings;
        setFuncSettings(newFuncSettings);
    }

    try {
      const res = await fetch('http://localhost:8005/parse', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
            code, 
            global_settings: newGlobalSettings,
            func_settings: newFuncSettings
        })
      });
      const data = await res.json();
      if (data.functions) {
        setFuncs(data.functions);
        
        // Если была выбрана функция, актуализируем ее (чтобы обновился SVG)
        if (activeFunc) {
            const updatedFunc = data.functions.find((f: FuncData) => f.name === activeFunc.name);
            setActiveFunc(updatedFunc || data.functions[0] || null);
        } else if (data.functions.length > 0) {
            setActiveFunc(data.functions[0]);
        } else {
            setActiveFunc(null);
        }
      }
    } catch (err) {
      console.error(err);
      alert("Ошибка при парсинге. Убедитесь, что Python FastAPI сервер запущен!");
    } finally {
      setLoading(false);
    }
  };

  const handleSettingChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, type, value, checked } = e.target;
    setCurrentPanelSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : (parseInt(value) || 0)
    }));
  };

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', flexDirection: 'row' }}>
      
      {/* Левая панель: настройки, код и дерево */}
      <div style={{ 
        width: '400px', 
        display: 'flex', 
        flexDirection: 'column', 
        borderRight: '1px solid #444', 
        background: '#f4f4f5', 
        color: '#222',
        padding: '15px'
      }}>
        
        <div style={{ background: '#fff', border: '1px solid #ddd', padding: '10px', borderRadius: '6px', marginBottom: '15px' }}>
            <h3 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>Параметры отрисовки</h3>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                <span>Ширина блоков (пикс.):</span>
                <input type="number" name="max_width" value={currentPanelSettings.max_width} onChange={handleSettingChange} style={{ width: '60px' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                <span>Горизонтальный интервал:</span>
                <input type="number" name="horiz_spacing" value={currentPanelSettings.horiz_spacing} onChange={handleSettingChange} style={{ width: '60px' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                <span>Вертикальный интервал:</span>
                <input type="number" name="vert_spacing" value={currentPanelSettings.vert_spacing} onChange={handleSettingChange} style={{ width: '60px' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                <span>Внутренние отступы блоков:</span>
                <input type="number" name="padding" value={currentPanelSettings.padding} onChange={handleSettingChange} style={{ width: '60px' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Размер шрифта:</span>
                <input type="number" name="font_size" value={currentPanelSettings.font_size} onChange={handleSettingChange} style={{ width: '60px' }} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', alignItems: 'center' }}>
                <span style={{ flex: 1 }}>Обход return вправо (для сложных схем):</span>
                <input
                  type="checkbox"
                  name="return_wide_route"
                  checked={currentPanelSettings.return_wide_route}
                  onChange={handleSettingChange}
                  style={{ width: '20px', height: '20px', cursor: 'pointer' }}
                />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', alignItems: 'center' }}>
                <span style={{ flex: 1 }}>Непрозрачные блоки (скрыть линии):</span>
                <input
                  type="checkbox"
                  name="fill_blocks"
                  checked={currentPanelSettings.fill_blocks}
                  onChange={handleSettingChange}
                  style={{ width: '20px', height: '20px', cursor: 'pointer' }}
                />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '8px', alignItems: 'center' }}>
                <span style={{ flex: 1 }}>Шахматный порядок (switch):</span>
                <input
                  type="checkbox"
                  name="staggered_switch"
                  checked={currentPanelSettings.staggered_switch}
                  onChange={handleSettingChange}
                  style={{ width: '20px', height: '20px', cursor: 'pointer' }}
                />
            </div>
            
            <div style={{ display: 'flex', gap: '5px', marginTop: '15px' }}>
                <button 
                  onClick={() => handleParse(true)} 
                  disabled={loading}
                  style={{ 
                    flex: 1,
                    padding: '8px', 
                    background: '#0ea5e9', 
                    color: '#fff', 
                    border: 'none', 
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '12px',
                    fontWeight: 'bold'
                  }}
                >
                  {loading ? 'Рендеринг...' : 'Применить ко всем'}
                </button>
                <button 
                  onClick={() => handleParse(false)} 
                  disabled={loading || !activeFunc}
                  style={{ 
                    flex: 1,
                    padding: '8px', 
                    background: '#10b981', 
                    color: '#fff', 
                    border: 'none', 
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '12px',
                    fontWeight: 'bold'
                  }}
                >
                  {loading ? 'Рендеринг...' : 'Только к текущей'}
                </button>
            </div>
        </div>

        <h3 style={{ margin: '0 0 5px 0' }}>C++ Code</h3>
        <textarea
          style={{ 
            flex: '0 0 140px', 
            background: '#fff', 
            color: '#333', 
            padding: '10px', 
            fontFamily: 'monospace',
            border: '1px solid #ccc',
            borderRadius: '4px',
            resize: 'none',
            outline: 'none'
          }}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Вставьте C++ код сюда..."
        />
        
        <h3 style={{ margin: '15px 0 5px 0' }}>Дерево функций</h3>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, overflowY: 'auto', flex: 1 }}>
          {funcs.map((f, i) => (
            <li 
              key={i} 
              onClick={() => setActiveFunc(f)}
              style={{
                padding: '8px 10px',
                background: activeFunc?.name === f.name ? '#e0f2fe' : 'transparent',
                borderLeft: activeFunc?.name === f.name ? '4px solid #0ea5e9' : '4px solid transparent',
                borderRadius: '0 4px 4px 0',
                cursor: 'pointer',
                marginBottom: '4px',
                transition: 'background 0.2s',
                fontWeight: activeFunc?.name === f.name ? 'bold' : 'normal'
              }}
            >
              <span style={{ color: '#0ea5e9', marginRight: '8px' }}>ƒ</span>
              {f.name}
              
              {funcSettings[f.name] && (
                <span style={{ float: 'right', fontSize: '10px', background: '#10b981', color: '#fff', padding: '2px 5px', borderRadius: '4px' }}>
                  custom
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      {/* Правая панель: блок-схема */}
      <div style={{ flex: 1, position: 'relative', background: '#fff' }}>
        {activeFunc ? (
          <FlowCanvas 
            key={activeFunc.name + (funcSettings[activeFunc.name] || globalSettings).font_size}
            svgString={activeFunc.svg} 
            title={activeFunc.name}
          />
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#888' }}>
            <p>Вставьте код C++ слева и нажмите "Применить ко всем"</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
