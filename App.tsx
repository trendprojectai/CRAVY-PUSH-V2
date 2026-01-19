
import React, { useState } from 'react';

// Reusable Components
const Card: React.FC<{ title: string; value: string | number; icon: string; color: string }> = ({ title, value, icon, color }) => (
  <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4 transition-all hover:shadow-md">
    <div className={`${color} w-12 h-12 rounded-full flex items-center justify-center text-white text-xl`}>
      <i className={`fas ${icon}`}></i>
    </div>
    <div>
      <p className="text-sm text-slate-500 font-medium uppercase tracking-wider">{title}</p>
      <p className="text-2xl font-bold text-slate-800">{value}</p>
    </div>
  </div>
);

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'overview' | 'code' | 'instructions'>('overview');

  const pythonCodeSnippet = `
# How to run:
# 1. Install requirements: pip install httpx beautifulsoup4 python-dotenv
# 2. Add your GOOGLE_API_KEY to .env
# 3. Run: python main.py
  `.trim();

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Navigation */}
      <nav className="bg-slate-900 text-white sticky top-0 z-50 shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <i className="fas fa-map-marked-alt text-amber-400 text-2xl"></i>
              <span className="text-xl font-bold tracking-tight">SohoData<span className="text-amber-400">Engine</span></span>
            </div>
            <div className="hidden md:flex gap-6 text-sm font-medium">
              <button 
                onClick={() => setActiveTab('overview')}
                className={`hover:text-amber-400 transition-colors ${activeTab === 'overview' ? 'text-amber-400' : ''}`}
              >
                Dashboard
              </button>
              <button 
                onClick={() => setActiveTab('code')}
                className={`hover:text-amber-400 transition-colors ${activeTab === 'code' ? 'text-amber-400' : ''}`}
              >
                Source Code
              </button>
              <button 
                onClick={() => setActiveTab('instructions')}
                className={`hover:text-amber-400 transition-colors ${activeTab === 'instructions' ? 'text-amber-400' : ''}`}
              >
                Run Guide
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Header Section */}
        <div className="mb-10">
          <h1 className="text-3xl font-extrabold text-slate-900 sm:text-4xl">
            Soho Restaurant Data Crawler
          </h1>
          <p className="mt-4 text-lg text-slate-600 max-w-3xl">
            A specialized ETL (Extract, Transform, Load) pipeline built for high-fidelity restaurant mapping. 
            It leverages the Google Places (New) API for geospatial accuracy and custom web crawling for menu discovery.
          </p>
        </div>

        {activeTab === 'overview' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <Card title="Target Area" value="Soho, London" icon="fa-location-dot" color="bg-blue-600" />
              <Card title="Estimated Places" value="~450" icon="fa-utensils" color="bg-emerald-600" />
              <Card title="Data Fields" value="11 Columns" icon="fa-table-list" color="bg-amber-600" />
              <Card title="Pipeline Status" value="Ready" icon="fa-circle-check" color="bg-slate-700" />
            </div>

            {/* Pipeline Preview */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
              <div className="bg-slate-50 px-6 py-4 border-b border-slate-200 flex justify-between items-center">
                <h3 className="font-bold text-slate-700">Data Schema Preview</h3>
                <span className="text-xs font-mono bg-slate-200 px-2 py-1 rounded">soho_restaurants_final.csv</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-500 uppercase font-semibold">
                    <tr>
                      <th className="px-6 py-3 border-b">google_place_id</th>
                      <th className="px-6 py-3 border-b">name</th>
                      <th className="px-6 py-3 border-b">postcode</th>
                      <th className="px-6 py-3 border-b">cuisine</th>
                      <th className="px-6 py-3 border-b">menu_url</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {[
                      { id: 'ChIJ...a1', name: 'Duck and Rice', pc: 'W1F 0RN', cuisine: 'Chinese', menu: 'https://...' },
                      { id: 'ChIJ...b2', name: 'Dishoom Carnaby', pc: 'W1B 5PW', cuisine: 'Indian', menu: 'https://...' },
                      { id: 'ChIJ...c3', name: 'Kiln', pc: 'W1D 7AW', cuisine: 'Thai', menu: 'https://...' },
                      { id: 'ChIJ...d4', name: 'The Palomar', pc: 'W1D 5BW', cuisine: 'Middle Eastern', menu: 'https://...' },
                    ].map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-50 transition-colors">
                        <td className="px-6 py-4 font-mono text-xs text-blue-600 truncate max-w-[120px]">{row.id}</td>
                        <td className="px-6 py-4 font-medium text-slate-900">{row.name}</td>
                        <td className="px-6 py-4 text-slate-600">{row.pc}</td>
                        <td className="px-6 py-4 text-slate-600">{row.cuisine}</td>
                        <td className="px-6 py-4 text-emerald-600 italic">Discovered via Crawler</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'code' && (
          <div className="space-y-6 animate-in slide-in-from-bottom-4 duration-500">
            <div className="bg-slate-900 rounded-xl p-6 text-slate-300 font-mono text-sm shadow-2xl overflow-hidden relative">
              <div className="flex gap-2 absolute top-4 right-4">
                <div className="w-3 h-3 rounded-full bg-red-500"></div>
                <div className="w-3 h-3 rounded-full bg-amber-500"></div>
                <div className="w-3 h-3 rounded-full bg-green-500"></div>
              </div>
              <h4 className="text-amber-400 mb-4 border-b border-slate-700 pb-2">Main Pipeline Logic (Preview)</h4>
              <pre className="whitespace-pre-wrap">
{`# Extraction Strategy
async def fetch_all_restaurants():
    places = await google.text_search("restaurants in Soho London")
    enriched_data = []
    for place in places:
        details = await google.get_details(place['id'])
        menu = await crawler.find_menu(details['website'])
        enriched_data.append(merge_fields(place, details, menu))
    
    save_to_csv(enriched_data, "soho_restaurants_final.csv")
`}
              </pre>
            </div>
            <p className="text-slate-500 italic text-center">Refer to the file listing in the output for complete production-grade source code.</p>
          </div>
        )}

        {activeTab === 'instructions' && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 space-y-6 animate-in fade-in duration-500">
             <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                <i className="fas fa-terminal text-blue-600"></i> Local Execution Guide
             </h3>
             <ol className="space-y-4 text-slate-600 list-decimal list-inside">
                <li className="pl-2"><span className="font-semibold text-slate-800">Environment:</span> Ensure Python 3.9+ is installed.</li>
                <li className="pl-2"><span className="font-semibold text-slate-800">Dependencies:</span> Install the requirements using `pip install -r requirements.txt`.</li>
                <li className="pl-2"><span className="font-semibold text-slate-800">API Key:</span> Create a `.env` file and paste `GOOGLE_API_KEY=YOUR_KEY_HERE`.</li>
                <li className="pl-2"><span className="font-semibold text-slate-800">Execution:</span> Run `python main.py` in your terminal.</li>
                <li className="pl-2"><span className="font-semibold text-slate-800">Output:</span> The script will generate `soho_restaurants_final.csv` in the current directory.</li>
             </ol>
             <div className="mt-8 p-4 bg-amber-50 border border-amber-200 rounded-lg">
                <p className="text-sm text-amber-800 flex gap-2">
                  <i className="fas fa-circle-info mt-1"></i>
                  The menu crawler respects robots.txt and includes a 5-second timeout per page to ensure compliance and avoid blocking.
                </p>
             </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="mt-20 border-t border-slate-200 py-8 bg-white">
        <div className="max-w-7xl mx-auto px-4 text-center text-slate-500 text-sm">
          <p>© 2024 Soho Restaurant Data Project - Built with React & Python</p>
        </div>
      </footer>
    </div>
  );
};

export default App;
