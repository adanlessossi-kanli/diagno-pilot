/**
 * Unit tests for MobileSymptomInput (REQ 10.1)
 *
 * Covers:
 *  a. Renders the symptom name input and "Ajouter" button
 *  b. Text input updates correctly on change
 *  c. Add button is disabled when name is empty
 *  d. Pressing "Ajouter" calls onAdd with the correct structured symptom
 *  e. After adding, the input is cleared
 *  f. Existing symptoms are rendered as tags
 *  g. Pressing the remove button on a tag calls onRemove with the correct index
 *  h. Severity selection updates the symptom severity
 *  i. Duration field is included in the structured symptom
 */
import React from 'react';
import { render, fireEvent, screen } from '@testing-library/react-native';
import { MobileSymptomInput } from '../MobileSymptomInput';
import type { Symptom } from '@diagno-pilot/types';

const noOp = () => {};

const makeSymptom = (name: string, severity = 'moderate', duration_days = 0): Symptom => ({
  name,
  severity,
  duration_days,
});

describe('MobileSymptomInput', () => {
  it('a. renders the symptom name input and add button', () => {
    render(<MobileSymptomInput symptoms={[]} onAdd={noOp} onRemove={noOp} />);
    expect(screen.getByPlaceholderText('Nom du symptôme')).toBeTruthy();
    expect(screen.getByLabelText('Ajouter le symptôme')).toBeTruthy();
  });

  it('b. text input updates on change', () => {
    render(<MobileSymptomInput symptoms={[]} onAdd={noOp} onRemove={noOp} />);
    const input = screen.getByPlaceholderText('Nom du symptôme');
    fireEvent.changeText(input, 'Fièvre');
    expect(input.props.value).toBe('Fièvre');
  });

  it('c. add button is disabled when name is empty', () => {
    render(<MobileSymptomInput symptoms={[]} onAdd={noOp} onRemove={noOp} />);
    const btn = screen.getByLabelText('Ajouter le symptôme');
    expect(btn.props.accessibilityState?.disabled ?? btn.props.disabled).toBeTruthy();
  });

  it('d. pressing add calls onAdd with the correct structured symptom', () => {
    const onAdd = jest.fn();
    render(<MobileSymptomInput symptoms={[]} onAdd={onAdd} onRemove={noOp} />);

    fireEvent.changeText(screen.getByPlaceholderText('Nom du symptôme'), 'Toux');
    fireEvent.press(screen.getByLabelText('Ajouter le symptôme'));

    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(onAdd).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Toux', severity: 'moderate' })
    );
  });

  it('e. input is cleared after adding a symptom', () => {
    render(<MobileSymptomInput symptoms={[]} onAdd={noOp} onRemove={noOp} />);
    const input = screen.getByPlaceholderText('Nom du symptôme');
    fireEvent.changeText(input, 'Céphalée');
    fireEvent.press(screen.getByLabelText('Ajouter le symptôme'));
    expect(input.props.value).toBe('');
  });

  it('f. existing symptoms are rendered as tags', () => {
    const symptoms = [makeSymptom('Fièvre'), makeSymptom('Toux', 'severe', 3)];
    render(<MobileSymptomInput symptoms={symptoms} onAdd={noOp} onRemove={noOp} />);
    expect(screen.getByText(/Fièvre/)).toBeTruthy();
    expect(screen.getByText(/Toux/)).toBeTruthy();
  });

  it('g. pressing remove on a tag calls onRemove with the correct index', () => {
    const onRemove = jest.fn();
    const symptoms = [makeSymptom('Fièvre'), makeSymptom('Toux')];
    render(<MobileSymptomInput symptoms={symptoms} onAdd={noOp} onRemove={onRemove} />);

    fireEvent.press(screen.getByLabelText('Supprimer Toux'));
    expect(onRemove).toHaveBeenCalledWith(1);
  });

  it('h. selecting a severity updates the symptom on add', () => {
    const onAdd = jest.fn();
    render(<MobileSymptomInput symptoms={[]} onAdd={onAdd} onRemove={noOp} />);

    fireEvent.press(screen.getByText('Sévère'));
    fireEvent.changeText(screen.getByPlaceholderText('Nom du symptôme'), 'Dyspnée');
    fireEvent.press(screen.getByLabelText('Ajouter le symptôme'));

    expect(onAdd).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Dyspnée', severity: 'severe' })
    );
  });

  it('i. duration field is included in the structured symptom', () => {
    const onAdd = jest.fn();
    render(<MobileSymptomInput symptoms={[]} onAdd={onAdd} onRemove={noOp} />);

    fireEvent.changeText(screen.getByPlaceholderText('Nom du symptôme'), 'Douleur');
    fireEvent.changeText(screen.getByPlaceholderText('Durée (jours)'), '5');
    fireEvent.press(screen.getByLabelText('Ajouter le symptôme'));

    expect(onAdd).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Douleur', duration_days: 5 })
    );
  });
});
