// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
import { TvConnectPage } from '../TvConnectPage';
import { TvRemotePage } from '../TvRemotePage';
import { encodeQrMatrix } from '../QrCodeSvg';
import {
  resolveDeviceRole,
  saveStoredController,
  saveStoredTvIdentity,
  readStoredTvIdentity,
  readStoredControllers,
  clearStoredTvIdentity,
} from '../storage';
import { ProfilePage } from '../../profile/ProfilePage';
import { useTVNav, activateFocusedTvElement, TV_FOCUSED_CLASS } from '../../../hooks/useTVNav';

const mockNavigate = vi.fn();
let mockSearch = '';

vi.mock('../../../router', () => ({
  useRouter: () => ({
    path: '/remote',
    search: mockSearch,
    navigate: mockNavigate,
    back: vi.fn(),
    matchRoute: () => ({ matches: false, params: {} }),
  }),
}));

vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({
    authenticated: true,
    username: 'alice',
    role: 'viewer',
    loading: false,
    error: null,
    isStorageOutage: false,
    refreshAuth: vi.fn(),
    logout: vi.fn(),
  }),
}));

const mockSearchTitles = vi.fn();
vi.mock('../../../api/catalogue', () => ({
  searchTitles: (...args: any[]) => mockSearchTitles(...args),
}));

const mockSendCommand = vi.fn(() => true);
const mockPlayOnTv = vi.fn(() => true);
const mockReconnectPhone = vi.fn();
const mockRefreshTvIdentity = vi.fn();
const mockRefreshPhoneControllers = vi.fn();
const mockSelectActiveTv = vi.fn();

vi.mock('../../watchlist', () => ({
  useWatchlist: () => ({
    items: [],
    itemCount: 3,
    isInList: () => false,
    addItem: vi.fn(),
    removeItem: vi.fn(),
    refresh: vi.fn(),
  }),
}));

let mockRemoteState: any = {
  deviceRole: 'phone',
  tvIdentity: null,
  tvWsStatus: 'connected',
  connectedControllerCount: 0,
  refreshTvIdentity: mockRefreshTvIdentity,
  publishTvPlaybackState: vi.fn(),
  registerPlayerCommandHandler: vi.fn(),
  registerMediaLaunchHandler: vi.fn(),
  registerNavigationHandler: vi.fn(),
  controllers: {},
  activeController: null,
  phoneWsStatus: 'connected',
  tvOnline: true,
  tvState: {
    status: 'PLAYING',
    mediaId: 101,
    currentTitle: 'Friends',
    currentEpisode: 'S01E01',
    isSeries: true,
    currentPosition: 1934,
    duration: 2535,
    isPlaying: true,
    volume: 0.9,
    muted: false,
    updatedAt: Math.floor(Date.now() / 1000),
  },
  lastAckMessage: null,
  refreshPhoneControllers: mockRefreshPhoneControllers,
  selectActiveTv: mockSelectActiveTv,
  reconnectPhone: mockReconnectPhone,
  sendCommand: mockSendCommand,
  playOnTv: mockPlayOnTv,
};

vi.mock('../TvRemoteContext', () => ({
  useTvRemote: () => mockRemoteState,
}));

const mockRegisterTv = vi.fn();
const mockStartPairing = vi.fn();
const mockCompletePairing = vi.fn();
const mockGetDevices = vi.fn();
const mockHeartbeat = vi.fn();
const mockRevoke = vi.fn();

vi.mock('../api', () => ({
  registerTvDevice: (...args: any[]) => mockRegisterTv(...args),
  startTvPairing: (...args: any[]) => mockStartPairing(...args),
  completeTvPairing: (...args: any[]) => mockCompletePairing(...args),
  getTvDevices: (...args: any[]) => mockGetDevices(...args),
  heartbeatTvDevice: (...args: any[]) => mockHeartbeat(...args),
  revokeTvController: (...args: any[]) => mockRevoke(...args),
  deleteTvDevice: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mockSearch = '';
  mockRemoteState = {
    ...mockRemoteState,
    deviceRole: 'phone',
    phoneWsStatus: 'connected',
    tvOnline: true,
    tvState: {
      status: 'PLAYING',
      mediaId: 101,
      currentTitle: 'Friends',
      currentEpisode: 'S01E01',
      isSeries: true,
      currentPosition: 1934,
      duration: 2535,
      isPlaying: true,
      volume: 0.9,
      muted: false,
      updatedAt: Math.floor(Date.now() / 1000),
    },
  };
  mockSearchTitles.mockResolvedValue({
    total: 1,
    has_more: false,
    items: [
      {
        id: 505,
        title: 'Inception (2010)',
        year: '2010',
        poster: null,
        quality: '1080p',
        imdb: '8.8',
        is_series: 0,
        source: 'yomovies',
      },
    ],
  });
  mockRegisterTv.mockResolvedValue({
    tv_id: 'tv_livingroom1',
    name: 'Living Room TV',
    device_secret: 'sec_abc123',
    last_seen_at: Math.floor(Date.now() / 1000),
    created_at: Math.floor(Date.now() / 1000),
    controllers: [],
  });
  mockStartPairing.mockResolvedValue({
    pairing_id: 'pair_xyz999',
    tv_id: 'tv_livingroom1',
    tv_name: 'Living Room TV',
    code: '583214',
    display_code: '583 214',
    pairing_token: 'tok_shortlived',
    qr_path: '/remote?pid=pair_xyz999&t=tok_shortlived',
    expires_at: Math.floor(Date.now() / 1000) + 180,
    ttl_seconds: 180,
  });
  mockCompletePairing.mockResolvedValue({
    paired: true,
    tv_id: 'tv_livingroom1',
    tv_name: 'Living Room TV',
    controller_id: 'ctrl_phone1',
    phone_name: 'Alice iPhone',
    role: 'primary',
    control_token: 'ctok_secure123',
    created_at: Math.floor(Date.now() / 1000),
  });
  mockGetDevices.mockResolvedValue({
    devices: [
      {
        tv_id: 'tv_livingroom1',
        name: 'Living Room TV',
        online: true,
        nearby: true,
        same_network: true,
        last_seen_at: Math.floor(Date.now() / 1000),
        created_at: Math.floor(Date.now() / 1000),
        controller_count: 0,
        controllers: [],
      },
      {
        tv_id: 'tv_bedroom2',
        name: 'Bedroom TV',
        online: true,
        nearby: true,
        same_network: true,
        last_seen_at: Math.floor(Date.now() / 1000),
        created_at: Math.floor(Date.now() / 1000),
        controller_count: 0,
        controllers: [],
      },
    ],
  });
  mockRevoke.mockResolvedValue({ ok: true, revoked_count: 1, tv_id: 'tv_livingroom1' });
});

afterEach(() => {
  cleanup();
});

describe('Phase 1: CINEMY TV Remote Pairing Foundation', () => {
  it('1. QR matrix encoder produces valid square QR matrix with finder patterns', () => {
    const matrix = encodeQrMatrix('https://cinemy.local/remote?pid=pair_123&t=tok_abc');
    expect(matrix.length).toBeGreaterThanOrEqual(25);
    expect(matrix.length).toBe(matrix[0].length);
    // Top-left finder pattern corner is dark
    expect(matrix[0][0]).toBe(true);
    expect(matrix[0][6]).toBe(true);
    expect(matrix[6][0]).toBe(true);
  });

  it('2. TvConnectPage registers persistent TV identity and displays QR code + 6-digit code', async () => {
    render(<TvConnectPage />);

    await waitFor(() => {
      expect(screen.getByTestId('tv-pairing-code').textContent).toBe('583 214');
      expect(screen.getByRole('img', { name: /QR code to pair Living Room TV/i })).toBeDefined();
    });

    expect(mockRegisterTv).toHaveBeenCalledTimes(1);
    expect(mockStartPairing).toHaveBeenCalledWith('tv_livingroom1');
    const saved = JSON.parse(localStorage.getItem('cinemy_tv_identity_v1') || '{}');
    expect(saved.tvId).toBe('tv_livingroom1');
    expect(saved.deviceSecret).toBe('sec_abc123');
  });

  it('3. TvRemotePage lists nearby TVs and completes pairing via 6-digit code fallback', async () => {
    render(<TvRemotePage />);

    await waitFor(() => {
      expect(screen.getByText('Living Room TV')).toBeDefined();
      expect(screen.getByText('Bedroom TV')).toBeDefined();
    });

    const input = screen.getByLabelText(/Enter 6-Digit TV Code/i);
    fireEvent.change(input, { target: { value: '583 214' } });
    fireEvent.click(screen.getByRole('button', { name: 'Connect to TV' }));

    await waitFor(() => {
      expect(mockCompletePairing).toHaveBeenCalledWith(
        expect.objectContaining({ code: '583214' })
      );
      expect(screen.getByTestId('active-tv-banner')).toBeDefined();
    });

    // Disconnect revokes controller and removes active banner
    fireEvent.click(screen.getByRole('button', { name: /Disconnect/i }));
    await waitFor(() => {
      expect(mockRevoke).toHaveBeenCalledWith('tv_livingroom1', 'ctrl_phone1');
      expect(screen.queryByTestId('active-tv-banner')).toBeNull();
    });
  });

  it('4. TvRemotePage auto-completes QR pairing when opened with ?pid=...&t=...', async () => {
    mockSearch = '?pid=pair_xyz999&t=tok_shortlived';
    render(<TvRemotePage />);

    await waitFor(() => {
      expect(mockCompletePairing).toHaveBeenCalledWith(
        expect.objectContaining({
          pairing_id: 'pair_xyz999',
          pairing_token: 'tok_shortlived',
        })
      );
      expect(screen.getByTestId('active-tv-banner')).toBeDefined();
    });
  });

  it('5. Connected TvRemotePage displays authoritative TV state, sends PLAY/PAUSE/SEEK/EPISODE/NAV commands, and launches Play on TV', async () => {
    localStorage.setItem(
      'cinemy_tv_controllers_v1',
      JSON.stringify({
        tv_livingroom1: {
          tvId: 'tv_livingroom1',
          tvName: 'Living Room TV',
          controllerId: 'ctrl_phone1',
          controlToken: 'ctok_secure123',
          phoneName: 'Alice iPhone',
          role: 'primary',
          pairedAt: 1700000000,
        },
      })
    );
    localStorage.setItem('cinemy_active_remote_tv_v1', 'tv_livingroom1');

    render(<TvRemotePage />);

    await waitFor(() => {
      expect(screen.getByText('Friends')).toBeDefined();
      expect(screen.getByText('S01E01')).toBeDefined();
      expect(screen.getByText('32:14')).toBeDefined();
      expect(screen.getByText('42:15')).toBeDefined();
    });

    // Transport commands
    fireEvent.click(screen.getByRole('button', { name: 'Pause TV' }));
    expect(mockSendCommand).toHaveBeenCalledWith({ command: 'PAUSE' });

    fireEvent.click(screen.getByRole('button', { name: 'Rewind 10 seconds' }));
    expect(mockSendCommand).toHaveBeenCalledWith({ command: 'SEEK_BACKWARD', seconds: 10 });

    fireEvent.click(screen.getByRole('button', { name: 'Forward 30 seconds' }));
    expect(mockSendCommand).toHaveBeenCalledWith({ command: 'SEEK_FORWARD', seconds: 30 });

    fireEvent.click(screen.getByRole('button', { name: /Next Episode/i }));
    expect(mockSendCommand).toHaveBeenCalledWith({ command: 'NEXT_EPISODE' });

    // Compact secondary Back & Home actions remain outside touchpad
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(mockSendCommand).toHaveBeenCalledWith({ command: 'BACK' });

    const homeBtns = screen.getAllByRole('button', { name: 'Home' });
    fireEvent.click(homeBtns[homeBtns.length - 1]);
    expect(mockSendCommand).toHaveBeenCalledWith({ command: 'HOME' });

    // Search CINEMY and click Play on TV
    const searchInput = screen.getByLabelText('Search CINEMY to Play on TV');
    fireEvent.change(searchInput, { target: { value: 'Inception' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => {
      expect(screen.getByText('Inception (2010)')).toBeDefined();
    });

    fireEvent.click(screen.getByRole('button', { name: /Play on TV/i }));
    expect(mockPlayOnTv).toHaveBeenCalledWith(
      expect.objectContaining({ id: 505, title: 'Inception (2010)', isSeries: false })
    );
  });

  it('6. Disconnected phone state shows TV disconnected and Reconnect button without clearing pairing', async () => {
    localStorage.setItem(
      'cinemy_tv_controllers_v1',
      JSON.stringify({
        tv_livingroom1: {
          tvId: 'tv_livingroom1',
          tvName: 'Living Room TV',
          controllerId: 'ctrl_phone1',
          controlToken: 'ctok_secure123',
          phoneName: 'Alice iPhone',
          role: 'primary',
          pairedAt: 1700000000,
        },
      })
    );
    localStorage.setItem('cinemy_active_remote_tv_v1', 'tv_livingroom1');
    mockRemoteState = {
      ...mockRemoteState,
      phoneWsStatus: 'disconnected',
      tvOnline: false,
    };

    render(<TvRemotePage />);

    await waitFor(() => {
      expect(screen.getByText('TV disconnected')).toBeDefined();
      expect(screen.getByRole('button', { name: 'Reconnect' })).toBeDefined();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Reconnect' }));
    expect(mockReconnectPhone).toHaveBeenCalledTimes(1);
  });

  it('7. TV Touchpad maps Tap -> SELECT and Swipes -> NAVIGATE_UP/DOWN/LEFT/RIGHT without accidental SELECT or duplicate events', async () => {
    localStorage.setItem(
      'cinemy_tv_controllers_v1',
      JSON.stringify({
        tv_livingroom1: {
          tvId: 'tv_livingroom1',
          tvName: 'Living Room TV',
          controllerId: 'ctrl_phone1',
          controlToken: 'ctok_secure123',
          phoneName: 'Alice iPhone',
          role: 'primary',
          pairedAt: 1700000000,
        },
      })
    );
    localStorage.setItem('cinemy_active_remote_tv_v1', 'tv_livingroom1');

    const nowSpy = vi.spyOn(Date, 'now');
    let clock = 10000;
    nowSpy.mockImplementation(() => clock);

    const { container } = render(<TvRemotePage />);
    const pad = await waitFor(() => screen.getByTestId('tv-touchpad'));

    // Accessible label + instructions exist
    expect(pad.getAttribute('aria-label')).toBe('TV navigation touchpad');
    expect(screen.getByText(/Swipe up, down, left, or right to navigate the TV/i)).toBeDefined();

    // Touchpad surface is scoped (page container does not disable scrolling globally)
    const pageContainer = container.querySelector('.tv-page-container') as HTMLElement;
    expect(pageContainer.className).not.toContain('tv-touchpad-surface');

    const fireTouchGesture = (x1: number, y1: number, x2: number, y2: number) => {
      clock += 200;
      fireEvent.touchStart(pad, { touches: [{ clientX: x1, clientY: y1 }] });
      // Intermediate moves must NOT emit commands continuously
      fireEvent.touchMove(pad, { touches: [{ clientX: (x1 + x2) / 2, clientY: (y1 + y2) / 2 }] });
      fireEvent.touchMove(pad, { touches: [{ clientX: x2, clientY: y2 }] });
      clock += 80;
      fireEvent.touchEnd(pad, { changedTouches: [{ clientX: x2, clientY: y2 }] });
    };

    // Tap -> SELECT
    fireTouchGesture(150, 150, 152, 149);
    expect(mockSendCommand).toHaveBeenCalledTimes(1);
    expect(mockSendCommand).toHaveBeenLastCalledWith({ command: 'SELECT' });

    // Swipe Up (finger starts lower, ends higher) -> NAVIGATE_DOWN only (natural scroll down, no accidental SELECT)
    fireTouchGesture(150, 200, 154, 110);
    expect(mockSendCommand).toHaveBeenCalledTimes(2);
    expect(mockSendCommand).toHaveBeenLastCalledWith({ command: 'NAVIGATE_DOWN' });

    // Swipe Down (finger starts higher, ends lower) -> NAVIGATE_UP only (natural scroll up)
    fireTouchGesture(150, 100, 148, 195);
    expect(mockSendCommand).toHaveBeenCalledTimes(3);
    expect(mockSendCommand).toHaveBeenLastCalledWith({ command: 'NAVIGATE_UP' });

    // Swipe Left (finger starts right, ends left) -> NAVIGATE_RIGHT only (natural scroll right)
    fireTouchGesture(220, 150, 120, 155);
    expect(mockSendCommand).toHaveBeenCalledTimes(4);
    expect(mockSendCommand).toHaveBeenLastCalledWith({ command: 'NAVIGATE_RIGHT' });

    // Swipe Right (finger starts left, ends right) -> NAVIGATE_LEFT only (natural scroll left)
    fireTouchGesture(100, 150, 210, 145);
    expect(mockSendCommand).toHaveBeenCalledTimes(5);
    expect(mockSendCommand).toHaveBeenLastCalledWith({ command: 'NAVIGATE_LEFT' });

    // Desktop keyboard fallback still works
    clock += 200;
    fireEvent.keyDown(pad, { key: 'ArrowUp' });
    expect(mockSendCommand).toHaveBeenCalledTimes(6);
    expect(mockSendCommand).toHaveBeenLastCalledWith({ command: 'NAVIGATE_UP' });

    nowSpy.mockRestore();
  });

  it('8. Home-page useTVNav moves visible focus (.tv-remote-focused) on ArrowRight/Down/Left/Up and SELECT activates focused card', () => {
    const clickedIds: string[] = [];
    const scrollSpy = vi.fn();

    const HomeNavHarness = () => {
      useTVNav({ isPlayerOpen: false });
      return (
        <div className="home-page-container">
          <div className="discovery-row-track">
            <div className="content-card" tabIndex={0} data-testid="card-r1-c1" onClick={() => clickedIds.push('r1-c1')}>Card 1</div>
            <div className="content-card" tabIndex={0} data-testid="card-r1-c2" onClick={() => clickedIds.push('r1-c2')}>Card 2</div>
          </div>
          <div className="discovery-row-track">
            <div className="content-card" tabIndex={0} data-testid="card-r2-c1" onClick={() => clickedIds.push('r2-c1')}>Card 3</div>
            <div className="content-card" tabIndex={0} data-testid="card-r2-c2" onClick={() => clickedIds.push('r2-c2')}>Card 4</div>
          </div>
        </div>
      );
    };

    render(<HomeNavHarness />);

    const mockRect = (el: HTMLElement, left: number, top: number) => {
      Object.defineProperty(el, 'offsetWidth', { configurable: true, value: 180 });
      Object.defineProperty(el, 'offsetHeight', { configurable: true, value: 260 });
      el.getBoundingClientRect = () =>
        ({ left, top, right: left + 180, bottom: top + 260, width: 180, height: 260, x: left, y: top, toJSON: () => {} }) as DOMRect;
      el.scrollIntoView = scrollSpy;
    };

    const r1c1 = screen.getByTestId('card-r1-c1');
    const r1c2 = screen.getByTestId('card-r1-c2');
    const r2c1 = screen.getByTestId('card-r2-c1');
    const r2c2 = screen.getByTestId('card-r2-c2');

    mockRect(r1c1, 20, 100);
    mockRect(r1c2, 220, 100);
    mockRect(r2c1, 20, 400);
    mockRect(r2c2, 220, 400);

    // First remote swipe on Home (focus starts on body) -> highlights first visible content-card
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(document.activeElement).toBe(r1c1);
    expect(r1c1.classList.contains(TV_FOCUSED_CLASS)).toBe(true);
    expect(scrollSpy).toHaveBeenCalled();

    // Swipe Right -> moves to r1c2
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(document.activeElement).toBe(r1c2);
    expect(r1c2.classList.contains(TV_FOCUSED_CLASS)).toBe(true);
    expect(r1c1.classList.contains(TV_FOCUSED_CLASS)).toBe(false);

    // Swipe Down -> moves to r2c2
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    expect(document.activeElement).toBe(r2c2);
    expect(r2c2.classList.contains(TV_FOCUSED_CLASS)).toBe(true);

    // Swipe Left -> moves to r2c1
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    expect(document.activeElement).toBe(r2c1);

    // Swipe Up -> moves back to r1c1
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
    expect(document.activeElement).toBe(r1c1);

    // Tap (SELECT) -> clicks focused Home card
    expect(activateFocusedTvElement()).toBe(true);
    expect(clickedIds).toEqual(['r1-c1']);

    // Mouse pointerdown clears TV focus outline class so mouse UX stays clean
    window.dispatchEvent(new Event('pointerdown'));
    expect(r1c1.classList.contains(TV_FOCUSED_CLASS)).toBe(false);
  });

  it('9. Home Hero navigation escapes 8px carousel dots downward to first content row instead of trapping horizontally', () => {
    const HeroEscapeHarness = () => {
      useTVNav({ isPlayerOpen: false });
      return (
        <div className="home-page-container">
          <section className="hero-fullbleed">
            <div className="hero-action-buttons">
              <button type="button" className="btn-hero-play" data-testid="hero-play">Play Now</button>
              <button type="button" className="btn-hero-watchlist" data-testid="hero-list">Add to List</button>
            </div>
            <div className="hero-pagination-bar">
              <button type="button" className="hero-dot-indicator active" data-testid="dot-0" />
              <button type="button" className="hero-dot-indicator" data-testid="dot-1" />
              <button type="button" className="hero-dot-indicator" data-testid="dot-2" />
            </div>
          </section>
          <div className="discovery-row-track">
            <div className="content-card" tabIndex={0} data-testid="first-row-card-1">Movie 1</div>
            <div className="content-card" tabIndex={0} data-testid="first-row-card-2">Movie 2</div>
          </div>
        </div>
      );
    };

    render(<HeroEscapeHarness />);

    const place = (el: HTMLElement, left: number, top: number, width: number, height: number) => {
      Object.defineProperty(el, 'offsetWidth', { configurable: true, value: width });
      Object.defineProperty(el, 'offsetHeight', { configurable: true, value: height });
      el.getBoundingClientRect = () =>
        ({ left, top, right: left + width, bottom: top + height, width, height, x: left, y: top, toJSON: () => {} }) as DOMRect;
      el.scrollIntoView = vi.fn();
    };

    const heroPlay = screen.getByTestId('hero-play');
    const heroList = screen.getByTestId('hero-list');
    const dot0 = screen.getByTestId('dot-0');
    const dot1 = screen.getByTestId('dot-1');
    const dot2 = screen.getByTestId('dot-2');
    const rowCard1 = screen.getByTestId('first-row-card-1');
    const rowCard2 = screen.getByTestId('first-row-card-2');

    place(heroPlay, 48, 340, 150, 44);
    place(heroList, 214, 340, 150, 44);
    // 8px-tall hero dots on exact same horizontal baseline
    place(dot0, 48, 404, 24, 8);
    place(dot1, 80, 404, 8, 8);
    place(dot2, 96, 404, 8, 8);
    // First Home content row below hero
    place(rowCard1, 48, 560, 180, 260);
    place(rowCard2, 248, 560, 180, 260);

    // Start focused on Play Now
    heroPlay.focus();
    // Horizontal inside hero: Right -> Add to List, Left -> Play Now
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(document.activeElement).toBe(heroList);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    expect(document.activeElement).toBe(heroPlay);

    // Down from Play Now -> closest dot under Play Now center (dot2), then Down again MUST escape to first content row (NOT ping-pong to another dot!)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    expect(document.activeElement).toBe(dot2);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    expect(document.activeElement).toBe(rowCard1);

    // Right in first content row -> rowCard2
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(document.activeElement).toBe(rowCard2);

    // Up from dot0 escapes back to heroPlay (NOT ping-pong to dot1!)
    dot0.focus();
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
    expect(document.activeElement).toBe(heroPlay);
  });

  it('10. Role-based Profile shortcuts & resolveDeviceRole priority (Cases A-F)', async () => {
    const sampleTvIdentity = { tvId: 'tv_abc12345', name: 'Living Room TV', deviceSecret: 'sec' };
    const sampleController = {
      tvId: 'tv_real9999',
      tvName: 'Living Room TV',
      controllerId: 'ctrl_phone123',
      controlToken: 'tok_xyz',
      phoneName: 'iPhone Remote',
      role: 'primary' as const,
      pairedAt: 1700000000,
    };
    const iphoneUA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15';
    const androidMobileUA = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36';
    const smartTvUA = 'Mozilla/5.0 (SMART-TV; Linux; Tizen 6.5) AppleWebKit/537.36';
    const desktopUA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0';

    // Case A — Normal phone (no tvIdentity, activeController present, iPhone UA) -> phone
    expect(resolveDeviceRole(null, sampleController, iphoneUA)).toBe('phone');

    // Case B — Phone with stale TV identity (CRITICAL regression: tvIdentity valid + activeController present + iPhone UA) -> phone
    expect(resolveDeviceRole(sampleTvIdentity, sampleController, iphoneUA)).toBe('phone');
    expect(resolveDeviceRole(sampleTvIdentity, { [sampleController.tvId]: sampleController }, desktopUA)).toBe('phone');

    // Case C — Mobile phone without controller (even if stale tvIdentity exists) -> phone
    expect(resolveDeviceRole(null, null, iphoneUA)).toBe('phone');
    expect(resolveDeviceRole(null, null, androidMobileUA)).toBe('phone');
    expect(resolveDeviceRole(sampleTvIdentity, null, iphoneUA)).toBe('phone');

    // Case D — Real Smart TV (tvIdentity valid or null, no controller, Smart TV UA) -> tv
    expect(resolveDeviceRole(sampleTvIdentity, null, smartTvUA)).toBe('tv');
    expect(resolveDeviceRole(null, null, smartTvUA)).toBe('tv');

    // Case E — Desktop / TV browser (both registered AND first-visit unregistered before /tv-connect) -> tv
    expect(resolveDeviceRole(sampleTvIdentity, null, desktopUA)).toBe('tv');
    expect(resolveDeviceRole(null, null, desktopUA)).toBe('tv');

    // Case F — Stale TV identity cleanup when saveStoredController() runs
    clearStoredTvIdentity();
    localStorage.clear();
    saveStoredTvIdentity(sampleTvIdentity);
    expect(readStoredTvIdentity()?.tvId).toBe('tv_abc12345');
    saveStoredController(sampleController);
    expect(readStoredTvIdentity()).toBeNull();
    expect(localStorage.getItem('cinemy_tv_identity_v1')).toBeNull();
    expect(readStoredControllers()[sampleController.tvId]?.controllerId).toBe('ctrl_phone123');

    // Phone role on ProfilePage -> TV Remote visible, Connect Phone (TV) hidden
    mockRemoteState = { ...mockRemoteState, deviceRole: 'phone' };
    const { unmount } = render(<ProfilePage />);
    expect(screen.getByRole('button', { name: /TV Remote/i })).toBeDefined();
    expect(screen.queryByRole('button', { name: /Connect Phone \(TV\)/i })).toBeNull();
    expect(screen.getByRole('button', { name: /My List/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Home & Continue Watching/i })).toBeDefined();
    unmount();

    // TV role on ProfilePage -> Connect Phone (TV) visible, TV Remote hidden
    mockRemoteState = { ...mockRemoteState, deviceRole: 'tv' };
    render(<ProfilePage />);
    expect(screen.getByRole('button', { name: /Connect Phone \(TV\)/i })).toBeDefined();
    expect(screen.queryByRole('button', { name: /TV Remote/i })).toBeNull();
    expect(screen.getByRole('button', { name: /My List/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /Home & Continue Watching/i })).toBeDefined();
  });

  it('11. Unpaired Phone on TvRemotePage shows No TV connected and Connect a TV CTA', async () => {
    mockRemoteState = { ...mockRemoteState, deviceRole: 'phone' };
    render(<TvRemotePage />);
    await waitFor(() => {
      expect(screen.getByText('No TV connected')).toBeDefined();
      expect(screen.getByRole('button', { name: 'Connect a TV' })).toBeDefined();
    });
  });
});
