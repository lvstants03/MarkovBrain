// Tab Navigation Logic
function switchTab(tabId) {
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    
    document.getElementById(tabId).classList.add('active');
    
    // Find the clicked nav item by its onclick attribute or text
    const clickedItem = Array.from(document.querySelectorAll('.nav-item')).find(item => 
        item.getAttribute('onclick') && item.getAttribute('onclick').includes(tabId)
    );
    if (clickedItem) {
        clickedItem.classList.add('active');
    }
}

// Modal Toggle Logic
function openAutomationModal() {
    document.getElementById('automationModal').classList.add('active');
}

function closeAutomationModal() {
    document.getElementById('automationModal').classList.remove('active');
}

function switchModalTab(tabId) {
    const tabs = ['console', 'bookmarklet', 'tampermonkey'];
    tabs.forEach(t => {
        const btn = document.getElementById('btnTab' + t.charAt(0).toUpperCase() + t.slice(1));
        const content = document.getElementById('tabContent' + t.charAt(0).toUpperCase() + t.slice(1));
        if (t === tabId) {
            btn.classList.add('active');
            btn.style.borderBottom = '2px solid var(--primary)';
            btn.style.color = 'var(--primary)';
            content.style.display = 'block';
        } else {
            btn.classList.remove('active');
            btn.style.borderBottom = 'none';
            btn.style.color = 'var(--text-muted)';
            content.style.display = 'none';
        }
    });
}

// Copy to Clipboard Helpers
function copyConsoleCode() {
    const code = document.getElementById('consoleCode');
    code.select();
    document.execCommand('copy');
    alert('Đã copy mã Console vào clipboard!');
}

function copyBookmarkletCode() {
    const code = document.getElementById('bookmarkletCode');
    code.select();
    document.execCommand('copy');
    alert('Đã copy mã Bookmarklet vào clipboard!');
}

function copyTampermonkeyCode() {
    const code = document.getElementById('tampermonkeyCode');
    code.select();
    document.execCommand('copy');
    alert('Đã copy mã Tampermonkey Script vào clipboard!');
}

let demoBetsCurrentPage = 1;
const demoBetsPageSize = 10;

function prevDemoBetsPage() {
    if (demoBetsCurrentPage > 1) {
        demoBetsCurrentPage--;
        fetchRealtimeData();
    }
}

function nextDemoBetsPage() {
    demoBetsCurrentPage++;
    fetchRealtimeData();
}

function exportDemoBets() {
    window.location.href = '/api/export/demo-bets';
}

// Main Real-Time Polling Logic
async function fetchRealtimeData() {
    let data = null;
    try {
        // 1. Fetch statistics and AI Recommendations
        const statsResponse = await fetch('/api/statistics?limit=500&t=' + Date.now());
        const statsData = await statsResponse.json();
        
        if (statsData.status === 'success') {
            data = statsData.data;
            
            // Sync active game dropdown and header title
            const activeVal = `${statsData.lottery_id}_${statsData.lottery_code}`;
            const gameSelect = document.getElementById('gameSelect');
            if (gameSelect && gameSelect.value !== activeVal && !gameSelect.matches(':focus')) {
                gameSelect.value = activeVal;
            }
            const gameNames = {
                '47_mb45g': 'Miền Bắc 45 Giây',
                '48_mb75g': 'Miền Bắc 75 Giây',
                '45_pmb5p': 'Miền Bắc 5 Phút'
            };
            const activeName = gameNames[activeVal] || statsData.lottery_code;
            
            const gameTitleElem = document.getElementById('activeGameTitle');
            if (gameTitleElem) {
                gameTitleElem.innerText = `(${activeName})`;
            }
            const activeGameLabelEl = document.getElementById('activeGameLabel');
            if (activeGameLabelEl) {
                activeGameLabelEl.innerText = activeName;
            }
            
            const drawLabel = document.getElementById('drawHistoryGameLabel');
            if (drawLabel) {
                drawLabel.innerText = `(${activeName})`;
            }
            const predLabel = document.getElementById('predHistoryGameLabel');
            if (predLabel) {
                predLabel.innerText = `(${activeName})`;
            }
            const socketLabel = document.getElementById('socketHistoryGameLabel');
            if (socketLabel) {
                socketLabel.innerText = `(${activeName})`;
            }
            document.getElementById('totalRecordsAnalyzed').innerText = data.total_records || 0;
            
            // Update Parity Streak Details
            const leStreak = data.streaks.le_streak;
            const parityStateName = leStreak.state === 'Le' ? 'Lẻ' : 'Chẵn';
            document.getElementById('streakParityText').innerText = `Đang bệt ${parityStateName} (${leStreak.count} kỳ) | Kỷ lục: ${leStreak.max_history} kỳ`;
            
            // Update Size Streak Details
            const taiStreak = data.streaks.tai_streak;
            const sizeStateName = taiStreak.state === 'Tai' ? 'Tài' : 'Xỉu';
            document.getElementById('streakSizeText').innerText = `Đang bệt ${sizeStateName} (${taiStreak.count} kỳ) | Kỷ lục: ${taiStreak.max_history} kỳ`;
            
            // Update Next-Issue Probabilities
            const nextIssue = data.prediction_for_next_issue || {};
            const probLe = nextIssue.le_probability;
            const probChan = nextIssue.chan_probability;
            const probTai = nextIssue.tai_probability;
            const probXiu = nextIssue.xiu_probability;

            document.getElementById('probLeVal').innerText = typeof probLe === 'number' ? `${(probLe * 100).toFixed(1)}%` : '-%';
            document.getElementById('probChanVal').innerText = typeof probChan === 'number' ? `${(probChan * 100).toFixed(1)}%` : '-%';
            document.getElementById('probTaiVal').innerText = typeof probTai === 'number' ? `${(probTai * 100).toFixed(1)}%` : '-%';
            document.getElementById('probXiuVal').innerText = typeof probXiu === 'number' ? `${(probXiu * 100).toFixed(1)}%` : '-%';

            // Update AI Parity Recommendation
            const parityRec = data.ai_recommendation.parity;
            const pBox = document.getElementById('parityRecBox');
            const pDecision = document.getElementById('parityDecision');
            const pBadge = document.getElementById('parityDecisionBadge');
            const pConf = document.getElementById('parityConfidence');
            const pBar = document.getElementById('parityConfidenceBar');
            const pRationale = document.getElementById('parityRationale');
            
            pDecision.innerText = parityRec.decision;
            pConf.innerText = `Độ tin cậy: ${parityRec.confidence}%`;
            pBar.style.width = `${parityRec.confidence}%`;
            pRationale.innerText = parityRec.rationale;
            
            if (parityRec.decision !== 'BỎ QUA') {
                pBox.className = 'rec-box win-recommendation';
                pBadge.className = 'decision-badge decision-buy';
                pBadge.innerText = 'BUY';
            } else {
                pBox.className = 'rec-box';
                pBadge.className = 'decision-badge decision-nobet';
                pBadge.innerText = 'NO BET';
            }
            
            // Update AI Size Recommendation
            const sizeRec = data.ai_recommendation.size;
            const sBox = document.getElementById('sizeRecBox');
            const sDecision = document.getElementById('sizeDecision');
            const sBadge = document.getElementById('sizeDecisionBadge');
            const sConf = document.getElementById('sizeConfidence');
            const sBar = document.getElementById('sizeConfidenceBar');
            const sRationale = document.getElementById('sizeRationale');
            
            sDecision.innerText = sizeRec.decision;
            sConf.innerText = `Độ tin cậy: ${sizeRec.confidence}%`;
            sBar.style.width = `${sizeRec.confidence}%`;
            sRationale.innerText = sizeRec.rationale;
            
            if (sizeRec.decision !== 'BỎ QUA') {
                sBox.className = 'rec-box win-recommendation';
                sBadge.className = 'decision-badge decision-buy';
                sBadge.innerText = 'BUY';
            } else {
                sBox.className = 'rec-box';
                sBadge.className = 'decision-badge decision-nobet';
                sBadge.innerText = 'NO BET';
            }
        }
        
        // 2. Fetch history of draws (15 records)
        const historyResponse = await fetch('/api/history?limit=15&t=' + Date.now());
        const historyData = await historyResponse.json();
        
        if (historyData.status === 'success') {
            const drawTableBody = document.getElementById('drawHistoryTable');
            drawTableBody.innerHTML = '';
            
            if (historyData.data.length === 0) {
                drawTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Không có dữ liệu xổ số trong bộ nhớ.</td></tr>`;
            } else {
                historyData.data.forEach(item => {
                    const hasNumbers = item.numbers && item.numbers.length > 0;
                    const balls = hasNumbers 
                        ? item.numbers.map(num => `<span class="ball">${num}</span>`).join('')
                        : `<span style="color: var(--text-muted); font-size: 0.8rem; font-style: italic;">Chỉ nạp thống kê</span>`;
                    const totalDisplay = hasNumbers ? item.total : '-';
                    const parityLabel = item.is_le ? 'Lẻ' : 'Chẵn';
                    const sizeLabel = item.is_tai ? 'Tài' : 'Xỉu';
                    const timeStr = item.time ? item.time : '-';
                    
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="font-weight: 600;">${item.issue}</td>
                        <td style="color: var(--text-muted); font-size: 0.85rem;">${timeStr}</td>
                        <td><div class="ball-container">${balls}</div></td>
                        <td style="font-weight: 600;">${totalDisplay}</td>
                        <td style="color: ${item.is_tai ? '#f59e0b' : '#38bdf8'}">${sizeLabel}</td>
                        <td style="color: ${item.is_le ? '#fb7185' : '#34d399'}">${parityLabel}</td>
                    `;
                    drawTableBody.appendChild(tr);
                });
            }
        }
        
        // 3. Fetch prediction results and win rates
        const predictionsResponse = await fetch('/api/predictions?limit=15&t=' + Date.now());
        const predData = await predictionsResponse.json();
        
        if (predData.status === 'success') {
            // Update AI Engine Badge
            const aiEngineBadge = document.getElementById('aiEngineBadge');
            if (aiEngineBadge && data && data.ai_recommendation) {
                const engine = data.ai_recommendation.engine || 'Heuristics (3-Layer)';
                aiEngineBadge.innerHTML = `<span class="badge-pulse" style="background-color: ${engine.includes('Gemini') ? '#34d399' : 'var(--primary)'};"></span>AI Engine: ${engine}`;
            }

            // Update Win Rates UI
            const stats = predData.stats;
            const overallWinRateEl = document.getElementById('overallWinRate');
            if (overallWinRateEl && stats && typeof stats.overall_win_rate === 'number') {
                overallWinRateEl.innerText = `${(stats.overall_win_rate * 100).toFixed(1)}%`;
            }
            
            document.getElementById('parityWinRate').innerText = `${(stats.parity.win_rate * 100).toFixed(1)}%`;
            document.getElementById('parityWinRatio').innerText = `${stats.parity.wins}/${stats.parity.total}`;
            
            document.getElementById('sizeWinRate').innerText = `${(stats.size.win_rate * 100).toFixed(1)}%`;
            document.getElementById('sizeWinRatio').innerText = `${stats.size.wins}/${stats.size.total}`;
            
            // Render prediction history table
            const predTableBody = document.getElementById('predictionHistoryTable');
            predTableBody.innerHTML = '';
            
            if (predData.data.length === 0) {
                predTableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">Chưa có lịch sử dự đoán cược nào.</td></tr>`;
            } else {
                predData.data.forEach(item => {
                    const hasP = item.predicted_parity && item.predicted_parity !== 'Không có' && item.predicted_parity !== 'BO QUA';
                    const hasS = item.predicted_size && item.predicted_size !== 'Không có' && item.predicted_size !== 'BO QUA';
                    const pEngine = hasP ? ` (${item.engine_used_parity || 'Heuristics'})` : '';
                    const sEngine = hasS ? ` (${item.engine_used_size || 'Heuristics'})` : '';
                    const pState = (item.predicted_parity === 'Le' ? 'Lẻ' : item.predicted_parity === 'Chan' ? 'Chẵn' : 'Không cược') + pEngine;
                    const sState = (item.predicted_size === 'Tai' ? 'Tài' : item.predicted_size === 'Xiu' ? 'Xỉu' : 'Không cược') + sEngine;
                    const timeStr = item.time ? item.time : '-';
                    const pConfStr = (item.predicted_parity !== 'Không có' && item.parity_confidence) ? `${item.parity_confidence}%` : '-';
                    const sConfStr = (item.predicted_size !== 'Không có' && item.size_confidence) ? `${item.size_confidence}%` : '-';
                    
                    let actualResultStr = '-';
                    if (item.actual_parity || item.actual_size) {
                        const actP = item.actual_parity === 'Le' ? 'Lẻ' : 'Chẵn';
                        const actS = item.actual_size === 'Tai' ? 'Tài' : 'Xỉu';
                        actualResultStr = `${actS} / ${actP}`;
                    }
                    
                    // Badges for Status
                    let statusBadgeHtml = '';
                    if (item.status_parity === 'pending' || item.status_size === 'pending') {
                        statusBadgeHtml = `<span class="status-badge status-pending">Đang chờ</span>`;
                    } else {
                        const isParityWin = item.status_parity === 'win';
                        const isSizeWin = item.status_size === 'win';
                        
                        if (item.status_parity === 'ignored' && item.status_size === 'ignored') {
                            statusBadgeHtml = `<span class="status-badge" style="background: rgba(255,255,255,0.05); color: var(--text-muted);">Bỏ qua</span>`;
                        } else {
                            let winCount = 0;
                            let lossCount = 0;
                            if (item.status_parity === 'win') winCount++;
                            if (item.status_parity === 'lose') lossCount++;
                            if (item.status_size === 'win') winCount++;
                            if (item.status_size === 'lose') lossCount++;
                            
                            if (lossCount === 0) {
                                statusBadgeHtml = `<span class="status-badge status-win">THẮNG</span>`;
                            } else if (winCount === 0) {
                                statusBadgeHtml = `<span class="status-badge status-lose">THUA</span>`;
                            } else {
                                statusBadgeHtml = `<span class="status-badge status-win" style="background: rgba(99, 102, 241, 0.2); color: var(--primary);">HÒA (1W/1L)</span>`;
                            }
                        }
                    }
                    
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="font-weight: 600;">${item.issue}</td>
                        <td style="color: var(--text-muted); font-size: 0.85rem;">${timeStr}</td>
                        <td style="color: ${item.predicted_parity !== 'Không có' ? '#a5b4fc' : 'var(--text-muted)'}">${pState}</td>
                        <td style="font-weight: 500; color: var(--text-muted);">${pConfStr}</td>
                        <td style="color: ${item.predicted_size !== 'Không có' ? '#a5b4fc' : 'var(--text-muted)'}">${sState}</td>
                        <td style="font-weight: 500; color: var(--text-muted);">${sConfStr}</td>
                        <td style="font-weight: 500;">${actualResultStr}</td>
                        <td>${statusBadgeHtml}</td>
                    `;
                    predTableBody.appendChild(tr);
                });
            }
        }
        
        // Fetch Balance & Demo Bets Info
        try {
            const balanceResponse = await fetch(`/api/balance?page=${demoBetsCurrentPage}&limit=${demoBetsPageSize}&t=${Date.now()}`);
            const balanceData = await balanceResponse.json();
            if (balanceData.status === 'success') {
                // Cập nhật nhãn phân trang
                const totalBets = balanceData.total_bets || 0;
                const totalPages = Math.ceil(totalBets / demoBetsPageSize) || 1;
                const pageTextEl = document.getElementById('demoBetsPageText');
                if (pageTextEl) {
                    pageTextEl.innerText = `Trang ${demoBetsCurrentPage} / ${totalPages}`;
                }
                
                const btnPrev = document.getElementById('btnPrevDemoPage');
                const btnNext = document.getElementById('btnNextDemoPage');
                if (btnPrev) btnPrev.disabled = demoBetsCurrentPage <= 1;
                if (btnNext) btnNext.disabled = demoBetsCurrentPage >= totalPages;

                // Thống kê lợi nhuận cạnh nút Excel
                const summary = balanceData.summary || {};
                const netProfit = summary.net_profit || 0;
                const netProfitEl = document.getElementById('demoNetProfitVal');
                if (netProfitEl) {
                    if (netProfit > 0) {
                        netProfitEl.style.color = 'var(--success)';
                        netProfitEl.innerText = `Lợi nhuận: +${netProfit.toLocaleString('vi-VN')} VND`;
                    } else if (netProfit < 0) {
                        netProfitEl.style.color = '#ef4444';
                        netProfitEl.innerText = `Lợi nhuận: ${netProfit.toLocaleString('vi-VN')} VND`;
                    } else {
                        netProfitEl.style.color = 'var(--text-muted)';
                        netProfitEl.innerText = `Lợi nhuận: 0 VND`;
                    }
                }
                const b = balanceData.balances;
                document.getElementById('realBalanceVal').innerText = `${b.real_balance.toLocaleString('vi-VN')} VND`;
                
                // Update sidebar balance display
                const sidebarRealBalEl = document.getElementById('sidebarRealBalanceVal');
                if (sidebarRealBalEl) {
                    sidebarRealBalEl.innerText = `${b.real_balance.toLocaleString('vi-VN')} VND`;
                }
                const sidebarDemoBalEl = document.getElementById('sidebarDemoBalanceVal');
                if (sidebarDemoBalEl) {
                    sidebarDemoBalEl.innerText = `${b.demo_balance.toLocaleString('vi-VN')} VND`;
                }

                const demoBalEl = document.getElementById('demoBalanceVal');
                demoBalEl.innerText = `${b.demo_balance.toLocaleString('vi-VN')} VND`;
                
                // Toggle overdraft banner
                const overdraftBanner = document.getElementById('overdraftWarningBanner');
                if (balanceData.is_bankrupt) {
                    overdraftBanner.style.display = 'block';
                    demoBalEl.style.color = '#ef4444';
                } else {
                    overdraftBanner.style.display = 'none';
                    demoBalEl.style.color = 'var(--primary)';
                }
                
                const betInput = document.getElementById('demoBetAmountInput');
                if (betInput && !betInput.matches(':focus')) {
                    betInput.value = b.demo_bet_amount.toLocaleString('vi-VN');
                }
                
                const strategySelect = document.getElementById('betStrategySelect');
                if (strategySelect && !strategySelect.matches(':focus')) {
                    strategySelect.value = b.demo_bet_strategy || 'fixed';
                }
                
                const maxStreak = balanceData.max_loss_streak_tolerated || 0;
                const maxStreakValEl = document.getElementById('maxStreakVal');
                const riskWarningTextEl = document.getElementById('riskWarningText');
                const riskAnalysisPanelEl = document.getElementById('riskAnalysisPanel');
                
                if (maxStreakValEl) {
                    maxStreakValEl.innerText = `${maxStreak} kỳ`;
                    
                    if (maxStreak >= 6) {
                        maxStreakValEl.style.color = 'var(--success)';
                        riskAnalysisPanelEl.style.background = 'rgba(16, 185, 129, 0.08)';
                        riskAnalysisPanelEl.style.borderColor = 'rgba(16, 185, 129, 0.2)';
                        riskWarningTextEl.innerText = 'Vốn rất an toàn! Khả năng chống chịu chuỗi gãy bệt tuyệt vời.';
                        riskWarningTextEl.style.color = 'var(--success)';
                    } else if (maxStreak >= 4) {
                        maxStreakValEl.style.color = '#f59e0b';
                        riskAnalysisPanelEl.style.background = 'rgba(245, 158, 11, 0.08)';
                        riskAnalysisPanelEl.style.borderColor = 'rgba(245, 158, 11, 0.2)';
                        riskWarningTextEl.innerText = 'Mức rủi ro trung bình. Hãy cẩn trọng nếu gặp dây gãy kéo dài.';
                        riskWarningTextEl.style.color = '#f59e0b';
                    } else {
                        maxStreakValEl.style.color = '#ef4444';
                        riskAnalysisPanelEl.style.background = 'rgba(239, 68, 68, 0.08)';
                        riskAnalysisPanelEl.style.borderColor = 'rgba(239, 68, 68, 0.2)';
                        riskWarningTextEl.innerText = 'Rủi ro RẤT CAO! Tài khoản có thể cháy nhanh chóng nếu chuỗi gãy liên tiếp xuất hiện.';
                        riskWarningTextEl.style.color = '#ef4444';
                    }
                }
                
                // Update next bet amount displays on the recommendation cards
                if (balanceData.next_bet_amounts) {
                    const n = balanceData.next_bet_amounts;
                    const parityNextBetEl = document.getElementById('parityNextBetVal');
                    const sizeNextBetEl = document.getElementById('sizeNextBetVal');

                    if (parityNextBetEl) {
                        const ri = balanceData.risk_info && balanceData.risk_info.parity;
                        let label = `${(n.parity || 0).toLocaleString('vi-VN')} VND`;
                        if (ri && ri.is_paused) {
                            label = 'TAM DUNG';
                            parityNextBetEl.style.color = '#f59e0b';
                        } else if (n.parity_streak > 0) {
                            label += ` (Thua x${n.parity_streak})`;
                            parityNextBetEl.style.color = '#ef4444';
                        } else {
                            parityNextBetEl.style.color = '#a5b4fc';
                        }
                        parityNextBetEl.innerText = label;
                    }

                    if (sizeNextBetEl) {
                        const ri = balanceData.risk_info && balanceData.risk_info.size;
                        let label = `${(n.size || 0).toLocaleString('vi-VN')} VND`;
                        if (ri && ri.is_paused) {
                            label = 'TAM DUNG';
                            sizeNextBetEl.style.color = '#f59e0b';
                        } else if (n.size_streak > 0) {
                            label += ` (Thua x${n.size_streak})`;
                            sizeNextBetEl.style.color = '#ef4444';
                        } else {
                            sizeNextBetEl.style.color = '#a5b4fc';
                        }
                        sizeNextBetEl.innerText = label;
                    }
                }

                // Render Capital Risk panel
                if (balanceData.risk_info) {
                    renderCapitalRiskPanel(balanceData.risk_info, balanceData.balances);
                }
                
                const demoBetsTable = document.getElementById('demoBetsTable');
                demoBetsTable.innerHTML = '';
                if (balanceData.demo_bets.length === 0) {
                    demoBetsTable.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted);">Chưa có lượt cược giả lập nào được đặt...</td></tr>`;
                } else {
                    balanceData.demo_bets.forEach(bet => {
                        const marketText = bet.market_type === 'parity' ? 'Chẵn/Lẻ' : 'Tài/Xỉu';
                        const statusClass = bet.status === 'win' ? 'status-win' : bet.status === 'lose' ? 'status-lose' : 'status-pending';
                        const statusText = bet.status === 'win' ? 'THẮNG' : bet.status === 'lose' ? 'THUA' : 'Đang chờ';
                        
                        let resultColor = 'var(--text-muted)';
                        let resultText = '-';
                        if (bet.status === 'win') {
                            resultColor = 'var(--success)';
                            resultText = '+' + bet.win_amount.toLocaleString('vi-VN');
                        } else if (bet.status === 'lose') {
                            resultColor = '#ef4444';
                            resultText = '-' + bet.amount.toLocaleString('vi-VN');
                        }
                        
                        let engineColor = 'var(--text-muted)';
                        const engineVal = bet.engine || 'Heuristics';
                        if (engineVal === 'Combined') {
                            engineColor = '#a5b4fc';
                        } else if (engineVal === 'Gemini') {
                            engineColor = '#34d399';
                        }

                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td style="color: var(--text-muted); font-size: 0.85rem;">${bet.time || '-'}</td>
                            <td style="font-weight: 600;">${bet.issue}</td>
                            <td>${marketText}</td>
                            <td style="color: #a5b4fc; font-weight: 500;">${bet.prediction}</td>
                            <td style="color: ${engineColor}; font-weight: 500;">${engineVal}</td>
                            <td style="text-align: right; font-weight: 500;">${bet.amount.toLocaleString('vi-VN')}</td>
                            <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                            <td style="text-align: right; color: ${resultColor}; font-weight: 600;">
                                ${resultText}
                            </td>
                            <td style="text-align: right; font-weight: 500;">${bet.balance_after.toLocaleString('vi-VN')}</td>
                        `;
                        demoBetsTable.appendChild(tr);
                    });
                }
                
                // Update Capital Collapses table
                const demoCollapsesTable = document.getElementById('demoCollapsesTable');
                if (demoCollapsesTable && balanceData.capital_collapses) {
                    demoCollapsesTable.innerHTML = '';
                    if (balanceData.capital_collapses.length === 0) {
                        demoCollapsesTable.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted);">Chua ghi nhan su kien gay quan ly von nao.</td></tr>`;
                    } else {
                        const stratLabels = balanceData.strategy_labels || {};
                        balanceData.capital_collapses.forEach(c => {
                            const marketText = c.market_type === 'parity' ? 'Chan/Le' : 'Tai/Xiu';
                            const stratText = stratLabels[c.strategy] || c.strategy || 'Co dinh';
                            const tr = document.createElement('tr');
                            tr.innerHTML = `
                                <td style="color: var(--text-muted); font-size: 0.85rem;">${c.time || '-'}</td>
                                <td style="font-weight: 600;">${c.issue}</td>
                                <td>${marketText}</td>
                                <td style="text-align: right; color: var(--danger); font-weight: 600;">Thua x${c.loss_streak}</td>
                                <td style="text-align: right; color: #fb7185; font-weight: 500;">${c.amount_required.toLocaleString('vi-VN')}</td>
                                <td style="text-align: right; font-weight: 500;">${c.balance_current.toLocaleString('vi-VN')}</td>
                                <td style="text-align: right; font-weight: 500;">${c.base_amount.toLocaleString('vi-VN')}</td>
                                <td style="color: var(--text-muted);">${stratText}</td>
                            `;
                            demoCollapsesTable.appendChild(tr);
                        });
                    }
                }
            }
        } catch (balanceError) {
            console.error("Error fetching balance data:", balanceError);
        }
        
        // 4. Update Socket status and next issue headers
        const drawHistoryTable = document.getElementById('drawHistoryTable');
        if (drawHistoryTable.rows[0] && drawHistoryTable.rows[0].cells[0] && drawHistoryTable.rows[0].cells[0].innerText !== 'Đang tải dữ liệu xổ số...') {
            const latestIssue = drawHistoryTable.rows[0].cells[0].innerText;
            const nextIssueStr = incrementIssueCode(latestIssue);
            document.getElementById('parityNextIssue').innerText = `Kỳ tiếp theo: ${nextIssueStr}`;
            document.getElementById('sizeNextIssue').innerText = `Kỳ tiếp theo: ${nextIssueStr}`;
        }
        
        // 5. Fetch socket history logs
        const socketResponse = await fetch('/api/socket/history?limit=15&t=' + Date.now());
        const socketData = await socketResponse.json();
        if (socketData.status === 'success') {
            const logTableBody = document.getElementById('socketLogsTable');
            logTableBody.innerHTML = '';
            if (socketData.data.length === 0) {
                logTableBody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">Chưa có nhật ký kết nối.</td></tr>`;
            } else {
                socketData.data.forEach(item => {
                    const date = new Date(item.timestamp * 1000);
                    const timeStr = date.toLocaleTimeString() + ' ' + date.toLocaleDateString();
                    
                    let badgeBg = 'rgba(239, 68, 68, 0.15)';
                    let badgeColor = '#ef4444';
                    let eventName = item.event;
                    if (item.event === 'connected') {
                        badgeBg = 'rgba(52, 211, 153, 0.15)';
                        badgeColor = '#34d399';
                        eventName = 'KẾT NỐI';
                    } else if (item.event === 'disconnected') {
                        badgeBg = 'rgba(239, 68, 68, 0.15)';
                        badgeColor = '#ef4444';
                        eventName = 'MẤT KẾT NỐI';
                    } else if (item.event === 'reconnecting') {
                        badgeBg = 'rgba(245, 158, 11, 0.15)';
                        badgeColor = '#f59e0b';
                        eventName = 'THỬ LẠI';
                    }
                    
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="color: var(--text-muted); font-size: 0.9rem; white-space: nowrap;">${timeStr}</td>
                        <td><span class="badge" style="background: ${badgeBg}; color: ${badgeColor}; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: 600; font-size: 0.75rem; border: none; display: inline-flex; align-items: center; justify-content: center; width: 110px; margin: 0;">${eventName}</span></td>
                        <td style="font-weight: 500;">${item.message}</td>
                    `;
                    logTableBody.appendChild(tr);
                });
            }
        }
        
        // 6. Fetch market analysis
        const marketResponse = await fetch('/api/market-analysis?limit=100&t=' + Date.now());
        const marketData = await marketResponse.json();
        if (marketData.status === 'success' && marketData.data) {
            const analysis = marketData.data;
            
            // Update latest block info
            const latestBlockStatusEl = document.getElementById('latestBlockStatus');
            const latestBlockWinRateEl = document.getElementById('latestBlockWinRate');
            
            if (analysis.blocks_30 && analysis.blocks_30.length > 0) {
                const latestBlock = analysis.blocks_30[0];
                latestBlockStatusEl.innerText = latestBlock.status;
                latestBlockStatusEl.style.color = latestBlock.status === 'Ổn định' ? 'var(--success)' : latestBlock.status === 'Hỗn loạn' ? '#ef4444' : '#f59e0b';
                latestBlockWinRateEl.innerText = `${latestBlock.win_rate}%`;
            } else {
                latestBlockStatusEl.innerText = '-';
                latestBlockWinRateEl.innerText = '-';
            }
            
            // Render blocks table
            const marketTableBody = document.getElementById('marketBlocksTable');
            marketTableBody.innerHTML = '';
            if (!analysis.blocks_30 || analysis.blocks_30.length === 0) {
                marketTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Chưa có đủ 30 kỳ để phân tích.</td></tr>`;
            } else {
                analysis.blocks_30.forEach(item => {
                    const statusColor = item.status === 'Ổn định' ? 'var(--success)' : item.status === 'Hỗn loạn' ? '#ef4444' : '#f59e0b';
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="font-weight: 600; font-size: 0.85rem;">${item.block_range}</td>
                        <td style="color: var(--text-muted); font-size: 0.8rem;">${item.time_range}</td>
                        <td>${item.total_bets}</td>
                        <td style="font-weight: 600;">${item.win_rate}%</td>
                        <td><span style="color: ${statusColor}; font-weight: 600; font-size: 0.85rem;">${item.status}</span></td>
                    `;
                    marketTableBody.appendChild(tr);
                });
            }
            
            // Render weird breaks table
            const weirdTableBody = document.getElementById('weirdBreaksTable');
            weirdTableBody.innerHTML = '';
            if (!analysis.weird_breaks || analysis.weird_breaks.length === 0) {
                weirdTableBody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">Không phát hiện kỳ gãy lạ nào.</td></tr>`;
            } else {
                analysis.weird_breaks.forEach(item => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td style="font-weight: 600; font-size: 0.85rem;">${item.issue}</td>
                        <td style="color: var(--text-muted); font-size: 0.8rem;">${item.time}</td>
                        <td style="font-size: 0.85rem; color: #fb7185; font-weight: 500;">${item.details.join(' | ')}</td>
                    `;
                    weirdTableBody.appendChild(tr);
                });
            }
        }
        
    } catch (err) {
        console.error("Error polling statistics details:", err);
    }
}

function incrementIssueCode(lastIssue) {
    if (!lastIssue) return '';
    try {
        return (BigInt(lastIssue) + 1n).toString();
    } catch (err) {
        return lastIssue;
    }
}

async function updateToken() {
    const token = document.getElementById('tokenInput').value.trim();
    const cfAuthToken = document.getElementById('cfAuthTokenInput').value.trim();
    const cookie = document.getElementById('cookieInput').value.trim();
    
    if (!token) {
        alert("Vui lòng dán token hợp lệ.");
        return;
    }
    try {
        const response = await fetch('/api/config-token', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                token: token,
                cf_auth_token: cfAuthToken || null,
                cookie: cookie || null
            })
        });
        const res = await response.json();
        if (res.status === 'success') {
            alert("Cập nhật Token và cấu hình HTTP Auth thành công!");
            document.getElementById('tokenInput').value = '';
            document.getElementById('cfAuthTokenInput').value = '';
            document.getElementById('cookieInput').value = '';
            fetchRealtimeData();
        } else {
            alert("Lỗi: " + res.message);
        }
    } catch (e) {
        alert("Không thể kết nối đến API: " + e);
    }
}

async function triggerReconnect() {
    try {
        const response = await fetch('/api/reconnect', {method: 'POST'});
        const res = await response.json();
        alert(res.message);
        fetchRealtimeData();
    } catch (e) {
        alert("Lỗi kết nối lại: " + e);
    }
}

async function changeGame() {
    const gameVal = document.getElementById('gameSelect').value;
    const [id, code] = gameVal.split('_');
    try {
        const response = await fetch('/api/config-lottery', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({lottery_id: parseInt(id), lottery_code: code})
        });
        const res = await response.json();
        if (res.status === 'success') {
            alert(`Đã chuyển đổi thành công sang game mới! Hệ thống đang tải lại dữ liệu...`);
            fetchRealtimeData();
        } else {
            alert("Lỗi: " + res.message);
        }
    } catch (e) {
        alert("Lỗi kết nối API: " + e);
    }
}

async function resetDemoBalance() {
    if (confirm("Bạn có chắc chắn muốn reset số dư giả lập về 10,000,000 VND và xóa toàn bộ lịch sử cược ảo không?")) {
        try {
            const response = await fetch('/api/balance/reset', { method: 'POST' });
            const res = await response.json();
            if (res.status === 'success') {
                alert(res.message);
                fetchRealtimeData();
            }
        } catch(e) {
            alert("Lỗi khi reset số dư: " + e);
        }
    }
}

async function clearDemoBets() {
    if (confirm("Bạn có chắc chắn muốn XÓA TOÀN BỘ hệ thống (kỳ quay, lịch sử dự đoán, nhật ký cược) và tải lại dữ liệu mới nhất không? (Số dư giả lập hiện tại sẽ được GIỮ NGUYÊN)")) {
        try {
            const response = await fetch('/api/balance/clear-bets', { method: 'POST' });
            const res = await response.json();
            if (res.status === 'success') {
                alert(res.message);
                fetchRealtimeData();
            }
        } catch(e) {
            alert("Lỗi khi xóa nhật ký cược: " + e);
        }
    }
}

// Capital Risk Panel Renderer
function renderCapitalRiskPanel(riskInfo, balances) {
    const el = document.getElementById('capitalRiskPanel');
    if (!el) return;

    const ri = riskInfo.size || riskInfo.parity || {};
    const strategy = ri.strategy || 'fixed';
    const isPaused = ri.is_paused;
    const pauseHours = ri.pause_remaining_hours || 0;
    const winRate = ((ri.win_rate_used || 0) * 100).toFixed(1);
    const ev = ri.ev_per_bet || 0;
    const evPct = (ev * 100).toFixed(2);
    const evColor = ev >= 0 ? '#34d399' : '#ef4444';
    const pctBal = ri.pct_of_balance || 0;
    const maxStreak = ri.max_streak_tolerated || 0;
    const expBal = (ri.expected_balance_after_100 || 0).toLocaleString('vi-VN');
    const expGrowth = ri.expected_growth_pct_100 || 0;
    const expGrowthColor = expGrowth >= 0 ? '#34d399' : '#ef4444';
    const dailyP = (riskInfo.parity || {}).daily_loss_count || 0;
    const dailyS = (riskInfo.size || {}).daily_loss_count || 0;
    const dailyLimit = ri.daily_loss_limit;

    const pauseMin = pauseHours * 60;
    const pauseText = pauseMin < 60
        ? `Con <strong>${pauseMin.toFixed(0)} phút</strong>`
        : `Con <strong>${pauseHours.toFixed(1)} giờ</strong>`;

    const pauseBanner = isPaused
        ? `<div style="background: rgba(245,158,11,0.15); border: 1px solid rgba(245,158,11,0.4); border-radius:8px; padding:0.6rem 0.9rem; margin-bottom:0.8rem; display:flex; align-items:center; gap:0.5rem;">
               <span style="font-size:1.1rem;">&#9888;</span>
               <span style="color:#f59e0b; font-weight:600;">ĐANG TẠM DỪNG — ${pauseText} để mở lại. Tự động bảo vệ tài khoản do sụt giảm quá 25% vốn.</span>
           </div>`
        : '';

    const dailyRow = dailyLimit !== null && dailyLimit !== undefined
        ? `<div style="display:flex;justify-content:space-between;padding:0.35rem 0;border-bottom:1px solid rgba(255,255,255,0.06);">
               <span style="color:var(--text-muted);">Thua trong 24h (Chan/Le / Tai/Xiu)</span>
               <span style="font-weight:600;color:${(dailyP>=dailyLimit||dailyS>=dailyLimit)?'#ef4444':'#a5b4fc'};">${dailyP} / ${dailyS} <span style="color:var(--text-muted);font-weight:400;">(gioi han: ${dailyLimit})</span></span>
           </div>`
        : '';

    el.innerHTML = `
        ${pauseBanner}
        <div style="font-size:0.82rem; color:var(--text-muted); margin-bottom:0.5rem; font-style:italic;">Du lieu tinh cho thi truong <strong>Tai/Xiu</strong> dua tren lich su du doan thuc te.</div>
        <div style="display:flex;justify-content:space-between;padding:0.35rem 0;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="color:var(--text-muted);">Win Rate thuc te</span>
            <span style="font-weight:600;color:#a5b4fc;">${winRate}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:0.35rem 0;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="color:var(--text-muted);">EV moi ky (x1.95)</span>
            <span style="font-weight:600;color:${evColor};">${ev >= 0 ? '+' : ''}${evPct}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:0.35rem 0;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="color:var(--text-muted);">% Von cuoc moi ky</span>
            <span style="font-weight:600;color:${pctBal > 10 ? '#f59e0b' : '#a5b4fc'};">${pctBal}%</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:0.35rem 0;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="color:var(--text-muted);">Chiu duoc thua lien tiep</span>
            <span style="font-weight:600;color:${maxStreak >= 6 ? 'var(--success)' : maxStreak >= 3 ? '#f59e0b' : '#ef4444'};">${maxStreak} ky</span>
        </div>
        ${dailyRow}
        <div style="display:flex;justify-content:space-between;padding:0.35rem 0;border-bottom:1px solid rgba(255,255,255,0.06);">
            <span style="color:var(--text-muted);">Du bao von sau 100 ky</span>
            <span style="font-weight:600;color:${expGrowthColor};">${expBal} VND <small>(${expGrowth >= 0 ? '+' : ''}${expGrowth}%)</small></span>
        </div>
        <div style="margin-top:0.6rem;font-size:0.78rem;color:var(--text-muted);">
            * Du bao mang tinh ly thuyet, gia dinh WR=${winRate}% giua lien tuc 100 ky. Thuc te co the khac.
        </div>
    `;
    el.style.display = 'block';
}

async function updateDemoBetAmount() {
    const input = document.getElementById('demoBetAmountInput');
    const cleanVal = input.value.replace(/[\.,]/g, '');
    const amount = parseFloat(cleanVal);
    const strategy = document.getElementById('betStrategySelect').value;

    if (isNaN(amount) || amount <= 0) {
        alert("Vui long nhap muc cuoc hop le!");
        return;
    }
    try {
        const response = await fetch('/api/balance/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                amount: amount,
                strategy: strategy
            })
        });
        const res = await response.json();
        if (res.status === 'success') {
            input.value = amount.toLocaleString('vi-VN');
            fetchRealtimeData();
        } else {
            alert(res.message);
        }
    } catch(e) {
        alert("Loi khi cap nhat muc cuoc: " + e);
    }
}

async function setManualDemoBalance() {
    const input = document.getElementById('demoBalanceEditInput');
    const cleanVal = input.value.replace(/[\.,]/g, '');
    const balance = parseFloat(cleanVal);
    if (isNaN(balance) || balance < 0) {
        alert("Vui long nhap so du gia lap hop le!");
        return;
    }
    try {
        const response = await fetch('/api/balance/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ demo_balance: balance })
        });
        const res = await response.json();
        if (res.status === 'success') {
            input.value = '';
            fetchRealtimeData();
            if (res.recommended_bet) {
                const panel = document.getElementById('smartBetRecommendPanel');
                const optionsEl = document.getElementById('smartBetOptions');
                const rec = res.recommended_bet;
                let html = '';
                if (rec.k5 !== undefined) {
                    // Martingale: hien thi k3/k4/k5
                    html = `
                        <div style="display:flex; justify-content:space-between; align-items:center; padding:0.2rem 0;">
                            <span style="color:var(--text-muted);">An toan cao (chiu 5 ky):</span>
                            <button class="btn btn-secondary" onclick="applyRecommendedBet(${rec.k5})" style="padding: 0.15rem 0.5rem; font-size: 0.78rem; color: var(--success); border-color: rgba(16,185,129,0.3);">${rec.k5.toLocaleString('vi-VN')} VND</button>
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center; padding:0.25rem 0.4rem; background:rgba(99,102,241,0.1); border-radius:6px; margin:0.1rem 0;">
                            <span style="color:#a5b4fc; font-weight:600;">Khuyen nghi (chiu 4 ky):</span>
                            <button class="btn" onclick="applyRecommendedBet(${rec.k4})" style="padding: 0.15rem 0.5rem; font-size: 0.78rem; font-weight:600;">${rec.k4.toLocaleString('vi-VN')} VND [Ap dung]</button>
                        </div>
                        <div style="display:flex; justify-content:space-between; align-items:center; padding:0.2rem 0;">
                            <span style="color:var(--text-muted);">Tich cuc (chiu 3 ky):</span>
                            <button class="btn btn-secondary" onclick="applyRecommendedBet(${rec.k3})" style="padding: 0.15rem 0.5rem; font-size: 0.78rem; color: var(--warning); border-color: rgba(245,158,11,0.3);">${rec.k3.toLocaleString('vi-VN')} VND</button>
                        </div>
                    `;
                } else if (rec.recommended !== undefined) {
                    // Kelly / Fixed fractional
                    html = `
                        <div style="display:flex; justify-content:space-between; align-items:center; padding:0.25rem 0.4rem; background:rgba(99,102,241,0.1); border-radius:6px;">
                            <span style="color:#a5b4fc; font-weight:600;">Goi y cuoc phu hop:</span>
                            <button class="btn" onclick="applyRecommendedBet(${rec.recommended})" style="padding: 0.15rem 0.5rem; font-size: 0.78rem; font-weight:600;">${rec.recommended.toLocaleString('vi-VN')} VND [Ap dung]</button>
                        </div>
                        <div style="font-size:0.78rem; color:var(--text-muted); margin-top:0.3rem;">${rec.note || ''}</div>
                    `;
                }
                if (html) {
                    optionsEl.innerHTML = html;
                    panel.style.display = 'block';
                }
            }
        } else {
            alert(res.message);
        }
    } catch (e) {
        alert("Loi khi cap nhat so du gia lap: " + e);
    }
}


async function applyRecommendedBet(amount) {
    const betInput = document.getElementById('demoBetAmountInput');
    betInput.value = amount.toLocaleString('vi-VN');
    document.getElementById('smartBetRecommendPanel').style.display = 'none';
    await updateDemoBetAmount();
}

function setQuickBetAmount(amt) {
    const input = document.getElementById('demoBetAmountInput');
    input.value = amt.toLocaleString('vi-VN');
    updateDemoBetAmount();
}

async function updateSocketStatus() {
    try {
        const statsResponse = await fetch('/api/statistics?limit=1&t=' + Date.now());
        const statsData = await statsResponse.json();
        
        const wsBadge = document.getElementById('wsStatusBadge');
        const sidebarWsBadge = document.getElementById('sidebarWsStatusBadge');
        
        if (statsData.status === 'success') {
            const wsState = statsData.ws_status || 'disconnected';
            let className = 'badge status-offline';
            let text = 'Socket: Disconnected';
            
            if (wsState === 'connected') {
                className = 'badge status-online';
                text = 'Socket: Connected';
            } else if (wsState === 'connecting') {
                className = 'badge status-connecting';
                text = 'Socket: Connecting';
            }
            
            if (wsBadge) {
                wsBadge.className = className;
                wsBadge.innerText = text;
            }
            if (sidebarWsBadge) {
                sidebarWsBadge.className = className;
                sidebarWsBadge.innerHTML = `<span class="badge-pulse"></span>${wsState === 'connected' ? 'Kết nối trực tiếp' : wsState === 'connecting' ? 'Đang kết nối...' : 'Đã ngắt kết nối'}`;
            }
        }
    } catch(e) {
        const wsBadge = document.getElementById('wsStatusBadge');
        if (wsBadge) {
            wsBadge.className = 'badge status-offline';
            wsBadge.innerText = 'Socket: Offline';
        }
        const sidebarWsBadge = document.getElementById('sidebarWsStatusBadge');
        if (sidebarWsBadge) {
            sidebarWsBadge.className = 'badge status-offline';
            sidebarWsBadge.innerHTML = '<span class="badge-pulse"></span>Ngoại tuyến';
        }
    }
}

async function triggerGameReload() {
    try {
        const response = await fetch('/api/script/reload', { method: 'POST' });
        const res = await response.json();
        alert(res.message);
    } catch (e) {
        alert("Lỗi gửi yêu cầu tải lại trang game: " + e);
    }
}

// Generate the codes dynamically on page load based on current window location
function generateAutomationCodes() {
    const host = window.location.origin;
    
    // 1. Console Code
    const consoleCode = `(function() {
    const OriginalWebSocket = window.WebSocket;
    window.WebSocket = function(url, protocols) {
        if (url.includes("token=")) {
            try {
                const token = url.split("token=")[1].split("&")[0];
                fetch('${host}/api/config-token', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        token: token,
                        cf_auth_token: null,
                        cookie: document.cookie || null
                    })
                })
                .then(r => r.json())
                .then(d => {
                    console.log("Successfully synced token with local bot!", d);
                })
                .catch(err => {
                    console.error("Failed to sync token with local bot:", err);
                });
            } catch(e) {
                console.error("Parsing token error:", e);
            }
        }
        return new OriginalWebSocket(url, protocols);
    };
    window.WebSocket.prototype = OriginalWebSocket.prototype;
    console.log("Token Auto-Sync active in Console! Go switch lottery games to trigger sync.");

    // Poll for reload commands from local server
    setInterval(function() {
        fetch('${host}/api/script/command')
        .then(r => r.json())
        .then(d => {
            if (d && d.command === 'reload') {
                console.log("Received reload command from local bot! Reloading page...");
                window.location.reload();
            }
        })
        .catch(e => {});
    }, 2000);
})();`;
    
    // 2. Bookmarklet Code (minified and wrapped in javascript:)
    const bookmarkletCode = `javascript:(function(){const O=window.WebSocket;window.WebSocket=function(u,p){if(u.includes("token=")){try{const t=u.split("token=")[1].split("&")[0];fetch("${host}/api/config-token",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:t,cf_auth_token:null,cookie:document.cookie||null})}).then(r=>r.json()).then(d=>alert("Đồng bộ token thành công!")).catch(e=>alert("Lỗi đồng bộ: "+e))}catch(e){}}return new O(u,p)};window.WebSocket.prototype=O.prototype;alert("Đã kích hoạt auto-intercept. Vui lòng click menu chọn lại game để đồng bộ!");setInterval(function(){fetch("${host}/api/script/command").then(r=>r.json()).then(d=>{if(d&&d.command==='reload')window.location.reload()}).catch(e=>{})},2000);})();`;
    
    // 3. Tampermonkey script code
    const tampermonkeyCode = `// ==UserScript==
// @name         EE88 Token Auto-Sync
// @namespace    http://tampermonkey.net/
// @version      0.3
// @description  Tu dong dong bo hoa token va HTTP Auth EE88 voi local Dashboard & nhan lenh tai lai trang
// @match        *://*.ee8833.me/*
// @grant        none
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    let storedToken = null;
    let storedCfAuthToken = null;

    // Gui thong tin WebSocket Token, cf-auth-token va Cookie ve local bot
    function syncToBot() {
        if (!storedToken) return;
        fetch('${host}/api/config-token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                token: storedToken,
                cf_auth_token: storedCfAuthToken || null,
                cookie: document.cookie || null
            })
        })
        .then(r => r.json())
        .then(d => {
            console.log("Successfully synced with local bot!", d);
        })
        .catch(err => {
            console.error("Failed to sync with local bot:", err);
        });
    }

    // 1. Hook WebSocket (Bat WS Token)
    const OriginalWebSocket = window.WebSocket;
    window.WebSocket = function(url, protocols) {
        if (url.includes("token=")) {
            try {
                storedToken = url.split("token=")[1].split("&")[0];
                syncToBot();
            } catch (e) {
                console.error("Error extracting token:", e);
            }
        }
        return new OriginalWebSocket(url, protocols);
    };
    window.WebSocket.prototype = OriginalWebSocket.prototype;

    // 2. Hook Fetch (Bat cf-auth-token tu yeu cau Fetch)
    const originalFetch = window.fetch;
    window.fetch = async function(resource, init) {
        if (init && init.headers) {
            let cfToken = null;
            if (init.headers['cf-auth-token']) {
                cfToken = init.headers['cf-auth-token'];
            } else if (init.headers.get && typeof init.headers.get === 'function') {
                cfToken = init.headers.get('cf-auth-token');
            }
            if (cfToken && cfToken !== storedCfAuthToken) {
                storedCfAuthToken = cfToken;
                console.log("Captured cf-auth-token (Fetch):", cfToken);
                syncToBot();
            }
        }
        return originalFetch.apply(this, arguments);
    };

    // 3. Hook XMLHttpRequest (Bat cf-auth-token tu yeu cau Axios/XHR)
    const OriginalXHR = window.XMLHttpRequest;
    window.XMLHttpRequest = function() {
        const xhr = new OriginalXHR();
        const originalSetRequestHeader = xhr.setRequestHeader;

        xhr.setRequestHeader = function(header, value) {
            if (header && header.toLowerCase() === 'cf-auth-token') {
                if (value !== storedCfAuthToken) {
                    storedCfAuthToken = value;
                    console.log("Captured cf-auth-token (XHR):", value);
                    syncToBot();
                }
            }
            return originalSetRequestHeader.apply(this, arguments);
        };
        return xhr;
    };

    // 4. Nhan lenh tai lai trang tu local bot
    setInterval(function() {
        fetch('${host}/api/script/command')
        .then(r => r.json())
        .then(d => {
            if (d && d.command === 'reload') {
                console.log("Received reload command from local bot! Reloading page...");
                window.location.reload();
            }
        })
        .catch(e => {});
    }, 2000);
})();`;

    document.getElementById('consoleCode').value = consoleCode;
    document.getElementById('bookmarkletCode').value = bookmarkletCode;
    document.getElementById('tampermonkeyCode').value = tampermonkeyCode;
}

// Auto format commas/dots for input fields on page load
document.addEventListener('DOMContentLoaded', () => {
    // 1. Initial actions
    fetchRealtimeData();
    updateSocketStatus();
    generateAutomationCodes();
    
    // 2. Setup intervals
    setInterval(fetchRealtimeData, 3000); // Poll recommendations & data every 3 seconds
    setInterval(updateSocketStatus, 5000); // Check socket status every 5 seconds
    
    // 3. Event Listeners for inputs
    const betInput = document.getElementById('demoBetAmountInput');
    if (betInput) {
        betInput.addEventListener('focus', function(e) {
            this.value = this.value.replace(/[\.,]/g, '');
        });
        betInput.addEventListener('blur', function(e) {
            let val = this.value.replace(/[\.,]/g, '');
            if (!isNaN(parseFloat(val)) && val.trim() !== '') {
                this.value = parseFloat(val).toLocaleString('vi-VN');
            }
        });
    }
    const balanceInput = document.getElementById('demoBalanceEditInput');
    if (balanceInput) {
        balanceInput.addEventListener('focus', function(e) {
            this.value = this.value.replace(/[\.,]/g, '');
        });
        balanceInput.addEventListener('blur', function(e) {
            let val = this.value.replace(/[\.,]/g, '');
            if (!isNaN(parseFloat(val)) && val.trim() !== '') {
                this.value = parseFloat(val).toLocaleString('vi-VN');
            }
        });
    }
});
