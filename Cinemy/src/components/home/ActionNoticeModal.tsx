import React from 'react';
import { X } from 'lucide-react';

export type ActionNoticeType = 'play' | 'mylist';

interface ActionNoticeModalProps {
  isOpen: boolean;
  type: ActionNoticeType;
  title: string;
  movieId?: number;
  onClose: () => void;
}

export const ActionNoticeModal: React.FC<ActionNoticeModalProps> = ({
  isOpen,
  type,
  title,
  movieId,
  onClose,
}) => {
  if (!isOpen) return null;

  const isPlay = type === 'play';

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="action-modal-title"
      onClick={onClose}
    >
      <div
        className="modal-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <span className="modal-badge">
            {isPlay ? 'Streaming Integration' : 'Watchlist Feature'}
          </span>
          <button
            type="button"
            className="modal-close-btn"
            onClick={onClose}
            aria-label="Close dialog"
          >
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>

        <h3 id="action-modal-title" className="modal-title">
          {title}
        </h3>

        <div className="modal-body">
          {isPlay ? (
            <p>
              The streaming player, HLS proxy, and multi-source provider resolver
              are scheduled for implementation in <strong>Phase 4</strong>.
              <br /><br />
              Target title ID <code>#{movieId}</code> is verified in the catalogue database.
              The existing Vanilla player remains active on the live site.
            </p>
          ) : (
            <p>
              <strong>My List</strong> requires user-bound watchlist persistence, which is not yet
              supported in the current SQLite schema.
              <br /><br />
              This control is currently in preview mode and does not persist saved titles.
            </p>
          )}
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="btn btn-primary"
            onClick={onClose}
            autoFocus
          >
            Understood
          </button>
        </div>
      </div>
    </div>
  );
};

