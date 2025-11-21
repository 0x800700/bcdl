import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Search, Download, Loader2, Music, CheckCircle, AlertCircle } from 'lucide-react';

function App() {
    const [url, setUrl] = useState('');
    const [status, setStatus] = useState('idle'); // idle, scanning, scanned, downloading, completed, error
    const [albums, setAlbums] = useState([]);
    const [selectedAlbums, setSelectedAlbums] = useState(new Set());
    const [jobId, setJobId] = useState(null);
    const [progress, setProgress] = useState([]);
    const [downloadStats, setDownloadStats] = useState(null);

    const handleScan = async () => {
        if (!url) return;
        setStatus('scanning');
        setProgress(['Starting scan...']);
        setAlbums([]);
        try {
            const res = await axios.post('http://localhost:8000/api/scan', { url });
            setJobId(res.data.job_id);
        } catch (err) {
            setStatus('error');
            setProgress(prev => [...prev, `Error starting scan: ${err.message}`]);
        }
    };

    const handleDownload = async () => {
        if (selectedAlbums.size === 0) return;
        setStatus('downloading');
        setProgress(['Starting download...']);
        try {
            const res = await axios.post('http://localhost:8000/api/download', {
                urls: Array.from(selectedAlbums)
            });
            setJobId(res.data.job_id);
        } catch (err) {
            setStatus('error');
            setProgress(prev => [...prev, `Error starting download: ${err.message}`]);
        }
    };

    const toggleAlbum = (albumUrl) => {
        const newSelected = new Set(selectedAlbums);
        if (newSelected.has(albumUrl)) {
            newSelected.delete(albumUrl);
        } else {
            newSelected.add(albumUrl);
        }
        setSelectedAlbums(newSelected);
    };

    const selectAll = () => {
        if (selectedAlbums.size === albums.length) {
            setSelectedAlbums(new Set());
        } else {
            setSelectedAlbums(new Set(albums.map(a => a.url)));
        }
    };

    useEffect(() => {
        let interval;
        if (jobId && (status === 'scanning' || status === 'downloading')) {
            interval = setInterval(async () => {
                try {
                    const res = await axios.get(`http://localhost:8000/api/jobs/${jobId}`);
                    const job = res.data;

                    // Update progress log
                    if (job.progress && job.progress.length > 0) {
                        // Just take the last few lines to avoid clutter if needed, or all
                        setProgress(job.progress);
                    }

                    // Update albums in real-time
                    if (job.type === 'scan' && job.result) {
                        setAlbums(job.result);
                    }

                    if (job.status === 'completed') {
                        if (job.type === 'scan') {
                            setStatus('scanned');
                            // Auto-select all by default
                            setSelectedAlbums(new Set(job.result.map(a => a.url)));
                        } else if (job.type === 'download') {
                            setStatus('completed');
                            setDownloadStats(job.result);
                        }
                        setJobId(null);
                    } else if (job.status === 'failed') {
                        setStatus('error');
                        setJobId(null);
                    }
                } catch (err) {
                    console.error("Polling error", err);
                }
            }, 1000);
        }
        return () => clearInterval(interval);
    }, [jobId, status]);

    return (
        <div className="min-h-screen bg-slate-900 text-slate-100 p-8 font-sans">
            <div className="max-w-6xl mx-auto space-y-8">

                {/* Header */}
                <header className="text-center space-y-2">
                    <h1 className="text-4xl font-bold bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                        Bandcamp Downloader
                    </h1>
                    <p className="text-slate-400">Dockerized & Modern</p>
                </header>

                {/* Input Section */}
                <div className="max-w-2xl mx-auto bg-slate-800/50 p-6 rounded-2xl backdrop-blur-sm border border-slate-700 shadow-xl">
                    <div className="flex gap-4">
                        <div className="relative flex-1">
                            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <Search className="h-5 w-5 text-slate-400" />
                            </div>
                            <input
                                type="text"
                                className="block w-full pl-10 pr-3 py-3 bg-slate-900 border border-slate-700 rounded-xl focus:ring-2 focus:ring-cyan-500 focus:border-transparent placeholder-slate-500 text-white transition-all"
                                placeholder="Enter Bandcamp Artist URL (e.g., https://artist.bandcamp.com)"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                disabled={status === 'scanning' || status === 'downloading'}
                            />
                        </div>
                        <button
                            onClick={handleScan}
                            disabled={status === 'scanning' || status === 'downloading' || !url}
                            className="px-6 py-3 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:cursor-not-allowed rounded-xl font-semibold transition-all flex items-center gap-2 shadow-lg shadow-cyan-900/20"
                        >
                            {status === 'scanning' ? <Loader2 className="animate-spin h-5 w-5" /> : <Search className="h-5 w-5" />}
                            Scan
                        </button>
                    </div>
                </div>

                {/* Progress / Status Area */}
                {(status === 'scanning' || status === 'downloading' || status === 'completed' || status === 'error') && (
                    <div className="max-w-2xl mx-auto bg-slate-900/50 p-4 rounded-xl border border-slate-800 font-mono text-sm text-slate-300 h-48 overflow-y-auto custom-scrollbar">
                        {progress.map((line, i) => (
                            <div key={i} className="mb-1">{line}</div>
                        ))}
                        {status === 'completed' && downloadStats && (
                            <div className="mt-4 p-3 bg-green-900/20 border border-green-800 rounded-lg text-green-400">
                                <p className="font-bold flex items-center gap-2"><CheckCircle className="h-4 w-4" /> Download Complete!</p>
                                <p>Downloaded: {downloadStats.downloaded}</p>
                                <p>Skipped: {downloadStats.skipped}</p>
                                <p>Failed: {downloadStats.failed}</p>
                            </div>
                        )}
                        {status === 'error' && (
                            <div className="mt-4 p-3 bg-red-900/20 border border-red-800 rounded-lg text-red-400">
                                <p className="font-bold flex items-center gap-2"><AlertCircle className="h-4 w-4" /> Operation Failed</p>
                            </div>
                        )}
                    </div>
                )}

                {/* Gallery Section */}
                {albums.length > 0 && (
                    <div className="space-y-4 animate-fade-in">
                        <div className="flex justify-between items-center px-4">
                            <h2 className="text-2xl font-semibold text-slate-200">
                                Found {albums.length} Albums
                            </h2>
                            <div className="flex gap-4">
                                <button
                                    onClick={selectAll}
                                    className="text-sm text-cyan-400 hover:text-cyan-300 font-medium"
                                >
                                    {selectedAlbums.size === albums.length ? 'Deselect All' : 'Select All'}
                                </button>
                                <button
                                    onClick={handleDownload}
                                    disabled={status === 'downloading' || selectedAlbums.size === 0}
                                    className="px-6 py-2 bg-green-600 hover:bg-green-500 disabled:bg-slate-700 rounded-lg font-semibold transition-all flex items-center gap-2 shadow-lg shadow-green-900/20"
                                >
                                    {status === 'downloading' ? <Loader2 className="animate-spin h-5 w-5" /> : <Download className="h-5 w-5" />}
                                    Download Selected ({selectedAlbums.size})
                                </button>
                            </div>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                            {albums.map((album, idx) => (
                                <div
                                    key={idx}
                                    onClick={() => toggleAlbum(album.url)}
                                    className={`
                    group relative aspect-square bg-slate-800 rounded-xl overflow-hidden cursor-pointer border-2 transition-all duration-200
                    ${selectedAlbums.has(album.url) ? 'border-cyan-500 ring-2 ring-cyan-500/20' : 'border-transparent hover:border-slate-600'}
                  `}
                                >
                                    {album.cover_url ? (
                                        <img src={album.cover_url} alt={album.title} className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center bg-slate-800 text-slate-600">
                                            <Music className="h-12 w-12" />
                                        </div>
                                    )}

                                    <div className="absolute inset-0 bg-gradient-to-t from-slate-900/90 via-slate-900/20 to-transparent opacity-100 transition-opacity">
                                        <div className="absolute top-2 left-2 flex gap-2">
                                            {album.price_status === 'paid' && (
                                                <span className="px-2 py-1 bg-red-500/80 text-white text-xs font-bold rounded backdrop-blur-sm">
                                                    PAID
                                                </span>
                                            )}
                                            {album.price_status === 'nyp' && (
                                                <span className="px-2 py-1 bg-blue-500/80 text-white text-xs font-bold rounded backdrop-blur-sm">
                                                    NYP
                                                </span>
                                            )}
                                            {album.price_status === 'free' && (
                                                <span className="px-2 py-1 bg-green-500/80 text-white text-xs font-bold rounded backdrop-blur-sm">
                                                    FREE
                                                </span>
                                            )}
                                        </div>
                                        <div className="absolute bottom-0 left-0 right-0 p-4">
                                            <h3 className="font-semibold text-white truncate" title={album.title}>{album.title}</h3>
                                            <p className="text-xs text-slate-400 truncate">{album.url}</p>
                                        </div>
                                    </div>

                                    {selectedAlbums.has(album.url) && (
                                        <div className="absolute top-3 right-3 bg-cyan-500 text-white p-1 rounded-full shadow-lg">
                                            <CheckCircle className="h-5 w-5" />
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default App;
