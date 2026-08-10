import { useState, useEffect } from 'react'

function App() {
  const [activeTab, setActiveTab] = useState('mod1')
  
  // Settings State
  const [provider, setProvider] = useState(() => localStorage.getItem('vefa_provider') || 'Ollama (Yerel)')
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('vefa_api_key') || '')
  const [modelName, setModelName] = useState(() => localStorage.getItem('vefa_model_name') || 'deepseek-r1:14b')
  const [ollamaHost, setOllamaHost] = useState(() => localStorage.getItem('vefa_ollama_host') || 'http://localhost:11434')

  const [query, setQuery] = useState('')
  const [limit, setLimit] = useState(20)
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)

  // Mod 2 State
  const [topic, setTopic] = useState('')
  const [academicLevel, setAcademicLevel] = useState('Yüksek Lisans Tezi')
  const [language, setLanguage] = useState('tr')
  const [targetWords, setTargetWords] = useState(5000)
  const [jobStatus, setJobStatus] = useState(null)

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/api/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query, limit, agent_mode: true }),
      });
      const data = await response.json();
      if (data.status === 'success') {
        setResults(data.results);
      }
    } catch (error) {
      console.error("API Hatası:", error);
    } finally {
      setLoading(false);
    }
  }

  const handleGenerate = async () => {
    if (!topic.trim()) return;
    try {
      await fetch('http://localhost:8000/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          topic, 
          academic_level: academicLevel, 
          language, 
          target_words: targetWords,
          provider,
          api_key: apiKey,
          model_name: modelName,
          ollama_host: ollamaHost
        }),
      });
    } catch (error) {
      console.error("API Hatası:", error);
    }
  }

  useEffect(() => {
    let interval;
    if (activeTab === 'mod2' || activeTab === 'mod3') {
      interval = setInterval(async () => {
        try {
          const res = await fetch('http://localhost:8000/api/status');
          const data = await res.json();
          setJobStatus(data.status);
        } catch (e) {}
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [activeTab]);

  return (
    <div className="app-container">
      <header className="animate-fade-in" style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: '15px', marginBottom: '1.5rem' }}>
        <img src="/vefa_logo.jpg" alt="VeFa Logo" style={{ width: '45px', height: '45px', borderRadius: '12px', objectFit: 'cover', boxShadow: '0 4px 15px rgba(100, 108, 255, 0.3)' }} />
        <h1 className="gradient-text" style={{ margin: 0 }}>VeFa Akademik Asistan</h1>
      </header>

      <div className="nav-tabs animate-fade-in" style={{ flexWrap: 'wrap' }}>
        <button 
          className={`nav-tab ${activeTab === 'mod1' ? 'active' : ''}`}
          onClick={() => setActiveTab('mod1')}
        >
          🔎 Mod 1: Kaynak Bulucu
        </button>
        <button 
          className={`nav-tab ${activeTab === 'mod2' ? 'active' : ''}`}
          onClick={() => setActiveTab('mod2')}
        >
          🚀 Mod 2: Tez Üretici
        </button>
        <button 
          className={`nav-tab ${activeTab === 'mod3' ? 'active' : ''}`}
          onClick={() => setActiveTab('mod3')}
        >
          🛠️ Mod 3: Denetle & Çevir
        </button>
        <button 
          className={`nav-tab ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          ⚙️ Ayarlar
        </button>
      </div>

      <main className="glass-panel animate-fade-in">
        {activeTab === 'settings' && (
          <div style={{ maxWidth: '600px', margin: '0 auto' }}>
            <h2 style={{ marginBottom: '2rem' }}>⚙️ Model ve API Ayarları</h2>
            
            <div className="form-group">
              <label className="form-label">Yapay Zeka Sağlayıcısı</label>
              <select className="form-input" value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option>Ollama (Yerel)</option>
                <option>Gemini</option>
                <option>OpenAI</option>
                <option>Anthropic</option>
                <option>Groq</option>
              </select>
            </div>

            {provider === 'Ollama (Yerel)' ? (
              <>
                <div className="form-group">
                  <label className="form-label">Ollama Sunucu Adresi</label>
                  <input type="text" className="form-input" value={ollamaHost} onChange={(e) => setOllamaHost(e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Ollama Model Adı</label>
                  <select className="form-input" value={modelName} onChange={(e) => setModelName(e.target.value)}>
                    <option value="deepseek-r1:1.5b">deepseek-r1:1.5b</option>
                    <option value="deepseek-r1:7b">deepseek-r1:7b</option>
                    <option value="deepseek-r1:8b">deepseek-r1:8b</option>
                    <option value="deepseek-r1:14b">deepseek-r1:14b</option>
                    <option value="deepseek-r1:32b">deepseek-r1:32b</option>
                    <option value="llama3">llama3</option>
                    <option value="llama3.1">llama3.1</option>
                    <option value="qwen2.5">qwen2.5</option>
                    <option value="mistral">mistral</option>
                    <option value="gemma2">gemma2</option>
                  </select>
                </div>
              </>
            ) : (
              <>
                <div className="form-group">
                  <label className="form-label">{provider} API Anahtarı (API Key)</label>
                  <input type="password" className="form-input" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." />
                </div>
                <div className="form-group">
                  <label className="form-label">Model Adı (İsteğe Bağlı)</label>
                  <input type="text" className="form-input" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="Varsayılan modeli kullanmak için boş bırakın..." />
                </div>
              </>
            )}
            
            <button className="btn btn-primary" style={{ width: '100%', marginTop: '1rem' }} onClick={() => {
              localStorage.setItem('vefa_provider', provider);
              localStorage.setItem('vefa_api_key', apiKey);
              localStorage.setItem('vefa_model_name', modelName);
              localStorage.setItem('vefa_ollama_host', ollamaHost);
              alert('Ayarlar tarayıcınıza kaydedildi! Sayfayı yenileseniz bile silinmeyecektir.');
            }}>
              💾 Ayarları Kaydet
            </button>
          </div>
        )}

        {activeTab === 'mod1' && (
          <div className="grid-2">
            <div>
              <h2>Akademik Kaynak Bulucu</h2>
              <p>Belirlediğiniz konu hakkında dünyadaki açık erişimli makale ve tezleri tarayarak PDF'leri otomatik indirir.</p>
              
              <div className="form-group" style={{ marginTop: '2rem' }}>
                <label className="form-label">Tez Konusu ve Başlıkları (İngilizce önerilir)</label>
                <textarea 
                  className="form-input" 
                  rows="4" 
                  placeholder="Örn: Artificial Intelligence in Healthcare..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                ></textarea>
              </div>

              <div className="form-group" style={{ marginTop: '1rem' }}>
                <label className="form-label">Maksimum İndirilecek PDF Sayısı</label>
                <input 
                  type="number" 
                  className="form-input" 
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value))}
                  min="1" 
                  max="50" 
                />
              </div>
              
              <button 
                className="btn btn-primary" 
                onClick={handleSearch}
                disabled={loading}
                style={{ width: '100%', marginTop: '1rem' }}
              >
                {loading ? '⏳ Aranıyor & İndiriliyor...' : '🚀 Arama ve İndirmeyi Başlat'}
              </button>
            </div>
            
            <div className="glass-panel" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <h3 style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem', marginBottom: '1rem' }}>
                📥 İndirilen Kaynaklar
              </h3>
              
              {results.length === 0 && !loading && (
                <div style={{ textAlign: 'center', opacity: 0.5, padding: '2rem 0' }}>
                  <span style={{ fontSize: '2rem', display: 'block', marginBottom: '1rem' }}>📚</span>
                  <p>Henüz arama yapılmadı.<br/>İndirilen PDF'ler burada listelenecek.</p>
                </div>
              )}

              {loading && (
                <div style={{ textAlign: 'center', padding: '2rem 0' }}>
                  <div className="spinner" style={{ margin: '0 auto 1rem', width: '30px', height: '30px', border: '3px solid rgba(255,255,255,0.1)', borderTopColor: '#3b82f6', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
                  <p>Yapay Zeka Kaynakları Tarıyor...</p>
                </div>
              )}

              {results.length > 0 && !loading && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  {results.map((item, idx) => (
                    <div key={idx} style={{ 
                      background: 'rgba(255,255,255,0.05)', 
                      padding: '1rem', 
                      borderRadius: '8px', 
                      borderLeft: item.status.includes('HATA') ? '4px solid #ef4444' : '4px solid #10b981' 
                    }}>
                      <h4 style={{ margin: '0 0 0.5rem', fontSize: '1rem' }}>📄 {item.title}</h4>
                      <div style={{ display: 'flex', gap: '1rem', fontSize: '0.8rem', opacity: 0.8 }}>
                        <span style={{ color: item.status.includes('HATA') ? '#ef4444' : '#10b981' }}>
                          {item.status.includes('HATA') ? '❌ ' + item.status : '✅ ' + item.status}
                        </span>
                        {item.url !== '#' && (
                           <a href={item.url} target="_blank" rel="noreferrer" style={{ color: '#3b82f6', textDecoration: 'none' }}>🔗 Dosya Konumu</a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Mod 2 Geliştirilmiş UI */}
        {activeTab === 'mod2' && (
          <div className="grid-2">
            <div>
              <p>Mod 1'den indirilen PDF kaynaklarını (RAG) okuyarak YÖK standartlarında yeni bir tez veya makale taslağı oluşturur.</p>
              
              <div className="form-group" style={{ marginTop: '2rem' }}>
                <label className="form-label">📌 Tez / Makale Konusu</label>
                <textarea 
                  className="form-input" 
                  rows="3" 
                  placeholder="Örn: Siber Güvenlik ve Hukuki Boyutları..."
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                ></textarea>
              </div>

              <div className="form-group">
                <label className="form-label">🎓 Akademik Seviye</label>
                <select className="form-input" value={academicLevel} onChange={(e) => setAcademicLevel(e.target.value)}>
                  <option>Yüksek Lisans Tezi</option>
                  <option>Doktora Tezi</option>
                  <option>Lisans Bitirme Tezi</option>
                  <option>Akademik Makale / Bildiri</option>
                </select>
              </div>
              
              <div className="form-group">
                <label className="form-label">🌐 Yazım Dili</label>
                <select className="form-input" value={language} onChange={(e) => setLanguage(e.target.value)}>
                  <option value="tr">Türkçe</option>
                  <option value="en">İngilizce</option>
                  <option value="ar">Arapça</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">📊 Hedef Kelime Sayısı</label>
                <input type="number" className="form-input" value={targetWords} step="500" onChange={(e) => setTargetWords(Number(e.target.value))} />
              </div>

              <button 
                className="btn btn-primary" 
                style={{ width: '100%', marginTop: '1rem' }}
                onClick={handleGenerate}
                disabled={jobStatus?.status === 'running'}
              >
                🚀 Akademik Tez/Makale Üretimini Başlat
              </button>
            </div>
            
            <div className="glass-panel" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <h3 style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem', marginBottom: '1rem' }}>
                📝 Üretim Durumu
              </h3>
              
              {!jobStatus ? (
                <div style={{ textAlign: 'center', opacity: 0.5, padding: '2rem 0' }}>
                  <span style={{ fontSize: '2rem', display: 'block', marginBottom: '1rem' }}>⚙️</span>
                  <p>Henüz bir üretim başlatılmadı.<br/>Sistem hazır olduğunda burada canlı durumu takip edebileceksiniz.</p>
                </div>
              ) : (
                <div style={{ padding: '1rem 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <strong>Durum:</strong> 
                    <span style={{ color: jobStatus.status === 'running' ? '#3b82f6' : (jobStatus.status === 'error' ? '#ef4444' : '#10b981') }}>
                      {jobStatus.status.toUpperCase()}
                    </span>
                  </div>
                  
                  <div style={{ marginBottom: '1rem', fontStyle: 'italic', opacity: 0.8 }}>
                    {jobStatus.step}
                  </div>
                  
                  {jobStatus.status === 'running' && (
                    <div style={{ width: '100%', background: 'rgba(255,255,255,0.1)', height: '8px', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: `${Math.max(5, jobStatus.progress * 100)}%`, background: 'var(--accent-gradient)', height: '100%', transition: 'width 0.5s ease' }}></div>
                    </div>
                  )}

                  {jobStatus.error && (
                    <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.2)', border: '1px solid #ef4444', borderRadius: '4px' }}>
                      <strong>Hata:</strong> {jobStatus.error}
                    </div>
                  )}

                  {jobStatus.docx_path && jobStatus.status === 'completed' && (
                    <div style={{ marginTop: '2rem' }}>
                      <a 
                        href={`http://localhost:8000/api/download?path=${encodeURIComponent(jobStatus.docx_path)}`} 
                        className="btn btn-primary" 
                        style={{ width: '100%', textAlign: 'center', display: 'block', textDecoration: 'none' }}
                      >
                        📄 YÖK Formatlı Word (.docx) İndir
                      </a>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Mod 3 Geliştirilmiş UI */}
        {activeTab === 'mod3' && (
          <div className="grid-2">
            <div>
              <h2>Akademik Belge Denetimi ve Çeviri</h2>
              <p>Mevcut bir Word belgesini yükleyin, yapay zeka ile dil düzeltmesi, YÖK formatı uyarlaması veya farklı bir dile akademik çevirisini yapın.</p>
              
              <div className="form-group" style={{ marginTop: '2rem' }}>
                <label className="form-label">📄 Word Belgesi (.docx) Yükle</label>
                <input 
                  type="file" 
                  className="form-input" 
                  accept=".docx"
                  id="mod3-file"
                />
              </div>

              <div className="form-group">
                <label className="form-label">🌐 Çeviri / İşlem Seçimi</label>
                <select className="form-input" id="mod3-lang">
                  <option value="same">Dili Değiştirme (Sadece Hata/Format Düzelt)</option>
                  <option value="tr">Türkçe'ye Çevir</option>
                  <option value="en">İngilizce'ye Çevir</option>
                  <option value="ar">Arapça'ya Çevir</option>
                </select>
              </div>

              <button 
                className="btn btn-primary" 
                style={{ width: '100%', marginTop: '1rem' }}
                onClick={async () => {
                  const fileInput = document.getElementById('mod3-file');
                  if (!fileInput.files.length) return alert('Lütfen bir dosya seçin');
                  const formData = new FormData();
                  formData.append('file', fileInput.files[0]);
                  formData.append('target_lang', document.getElementById('mod3-lang').value);
                  formData.append('provider', provider);
                  formData.append('api_key', apiKey);
                  formData.append('model_name', modelName);
                  formData.append('ollama_host', ollamaHost);
                  await fetch('http://localhost:8000/api/review', {
                    method: 'POST',
                    body: formData
                  });
                }}
                disabled={jobStatus?.status === 'running'}
              >
                🛠️ Akademik Denetleme / Çeviri Başlat
              </button>
            </div>
            
            <div className="glass-panel" style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <h3 style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem', marginBottom: '1rem' }}>
                📝 İşlem Durumu
              </h3>
              
              {!jobStatus ? (
                <div style={{ textAlign: 'center', opacity: 0.5, padding: '2rem 0' }}>
                  <span style={{ fontSize: '2rem', display: 'block', marginBottom: '1rem' }}>⚙️</span>
                  <p>Henüz bir işlem başlatılmadı.</p>
                </div>
              ) : (
                <div style={{ padding: '1rem 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <strong>Durum:</strong> 
                    <span style={{ color: jobStatus.status === 'running' ? '#3b82f6' : (jobStatus.status === 'error' ? '#ef4444' : '#10b981') }}>
                      {jobStatus.status.toUpperCase()}
                    </span>
                  </div>
                  
                  <div style={{ marginBottom: '1rem', fontStyle: 'italic', opacity: 0.8 }}>
                    {jobStatus.step}
                  </div>
                  
                  {jobStatus.status === 'running' && (
                    <div style={{ width: '100%', background: 'rgba(255,255,255,0.1)', height: '8px', borderRadius: '4px', overflow: 'hidden' }}>
                      <div style={{ width: `${Math.max(5, jobStatus.progress * 100)}%`, background: 'var(--accent-gradient)', height: '100%', transition: 'width 0.5s ease' }}></div>
                    </div>
                  )}

                  {jobStatus.error && (
                    <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.2)', border: '1px solid #ef4444', borderRadius: '4px' }}>
                      <strong>Hata:</strong> {jobStatus.error}
                    </div>
                  )}

                  {jobStatus.docx_path && jobStatus.status === 'completed' && (
                    <div style={{ marginTop: '2rem' }}>
                      <a 
                        href={`http://localhost:8000/api/download?path=${encodeURIComponent(jobStatus.docx_path)}`} 
                        className="btn btn-primary" 
                        style={{ width: '100%', textAlign: 'center', display: 'block', textDecoration: 'none' }}
                      >
                        📄 İşlenmiş Word (.docx) Dosyasını İndir
                      </a>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      <style dangerouslySetInnerHTML={{__html: `
        @keyframes spin { 100% { transform: rotate(360deg); } }
      `}} />
    </div>
  )
}

export default App
