import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/react';
import React from 'react';
import { ConfirmDialog } from '../ConfirmDialog';

afterEach(() => {
  cleanup();
});

const defaultProps = {
  open: true,
  title: 'Delete session?',
  message: 'This action cannot be undone.',
  confirmLabel: 'Delete',
  cancelLabel: 'Cancel',
  onConfirm: vi.fn(),
  onCancel: vi.fn(),
};

describe('ConfirmDialog', () => {
  it('renders nothing when open is false', () => {
    const { container } = render(
      <ConfirmDialog {...defaultProps} open={false} />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders the dialog with correct ARIA attributes when open', () => {
    const { container } = render(<ConfirmDialog {...defaultProps} />);
    const dialog = container.querySelector('[role="alertdialog"]');
    expect(dialog).not.toBeNull();
    expect(dialog?.getAttribute('aria-modal')).toBe('true');
    expect(dialog?.getAttribute('aria-labelledby')).toBe('confirm-dialog-title');
    expect(dialog?.getAttribute('aria-describedby')).toBe('confirm-dialog-message');
  });

  it('displays the title and message', () => {
    const { getByText } = render(<ConfirmDialog {...defaultProps} />);
    expect(getByText('Delete session?')).toBeDefined();
    expect(getByText('This action cannot be undone.')).toBeDefined();
  });

  it('displays confirm and cancel buttons with correct labels', () => {
    const { getByText } = render(<ConfirmDialog {...defaultProps} />);
    expect(getByText('Delete')).toBeDefined();
    expect(getByText('Cancel')).toBeDefined();
  });

  it('calls onConfirm when confirm button is clicked', () => {
    const onConfirm = vi.fn();
    const { getByText } = render(
      <ConfirmDialog {...defaultProps} onConfirm={onConfirm} />,
    );
    fireEvent.click(getByText('Delete'));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn();
    const { getByText } = render(
      <ConfirmDialog {...defaultProps} onCancel={onCancel} />,
    );
    fireEvent.click(getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('calls onCancel when backdrop is clicked', () => {
    const onCancel = vi.fn();
    const { container } = render(
      <ConfirmDialog {...defaultProps} onCancel={onCancel} />,
    );
    const backdrop = container.querySelector('[aria-hidden="true"]');
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop!);
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('calls onCancel when Escape key is pressed', () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...defaultProps} onCancel={onCancel} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('focuses the cancel button on open', async () => {
    const { getByText } = render(<ConfirmDialog {...defaultProps} />);
    // requestAnimationFrame is used, so we wait a tick
    await new Promise((r) => requestAnimationFrame(r));
    expect(document.activeElement).toBe(getByText('Cancel'));
  });

  it('traps focus within the dialog on Tab', async () => {
    const { getByText } = render(<ConfirmDialog {...defaultProps} />);
    await new Promise((r) => requestAnimationFrame(r));

    const cancelBtn = getByText('Cancel');
    const confirmBtn = getByText('Delete');

    // Focus is on cancel, Tab should move to confirm
    fireEvent.keyDown(document, { key: 'Tab' });
    // After Tab from cancel, focus should wrap or move to confirm
    // Since we're on cancel (first), Tab goes to confirm (last)
    cancelBtn.focus();
    fireEvent.keyDown(document, { key: 'Tab' });

    // Tab from confirm (last) should wrap to cancel (first)
    confirmBtn.focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(cancelBtn);
  });

  it('traps focus within the dialog on Shift+Tab', async () => {
    const { getByText } = render(<ConfirmDialog {...defaultProps} />);
    await new Promise((r) => requestAnimationFrame(r));

    const cancelBtn = getByText('Cancel');
    const confirmBtn = getByText('Delete');

    // Shift+Tab from cancel (first) should wrap to confirm (last)
    cancelBtn.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(confirmBtn);
  });

  it('renders a backdrop overlay', () => {
    const { container } = render(<ConfirmDialog {...defaultProps} />);
    const backdrop = container.querySelector('.bg-black\\/40');
    expect(backdrop).not.toBeNull();
  });
});
