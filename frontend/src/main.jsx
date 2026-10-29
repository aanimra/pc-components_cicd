import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

const blank = { name: '', price: '', category: '', model: '', stock_quantity: 0, product_type: '', description: '' }

async function request(url, options = {}) {
  const result = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options })
  if (!result.ok) {
    const details = await result.json().catch(() => ({}))
    throw new Error(typeof details.detail === 'string' ? details.detail : `HTTP ${result.status}`)
  }
  return result.status === 204 ? null : result.json()
}

function App() {
  const [items, setItems] = useState([])
  const [form, setForm] = useState(blank)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function refresh() {
    setLoading(true)
    try { setItems(await request('/api/items')); setError('') }
    catch (e) { setError(`Не вдалося отримати товари: ${e.message}`) }
    finally { setLoading(false) }
  }

  useEffect(() => { refresh() }, [])

  async function save(event) {
    event.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form, name: form.name.trim(), price: Number(form.price), stock_quantity: Number(form.stock_quantity) }
      await request(editingId ? `/api/items/${editingId}` : '/api/items', {
        method: editingId ? 'PUT' : 'POST', body: JSON.stringify(payload)
      })
      setForm(blank); setEditingId(null); await refresh()
    } catch (e) { setError(`Помилка збереження: ${e.message}`) }
    finally { setSaving(false) }
  }

  function edit(item) {
    setEditingId(item.id)
    setForm({ ...item })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function remove(item) {
    if (!window.confirm(`Видалити «${item.name}»?`)) return
    try { await request(`/api/items/${item.id}`, { method: 'DELETE' }); await refresh() }
    catch (e) { setError(`Помилка видалення: ${e.message}`) }
  }

  return <main className="layout">
    <header><span className="eyebrow">LAB 04 · Kubernetes · Helm</span><h1>PC Components</h1>
      <p>Каталог комплектуючих із повноцінними операціями CRUD та зберіганням у PostgreSQL.</p></header>
    <section className="panel">
      <h2>{editingId ? `Редагування товару #${editingId}` : 'Додати комплектуючу'}</h2>
      <form onSubmit={save}>
        <div className="fields">
          {[
            ['name', 'Назва *', 'text'], ['price', 'Ціна (грн) *', 'number'],
            ['category', 'Категорія', 'text'], ['model', 'Модель', 'text'],
            ['stock_quantity', 'Кількість на складі', 'number'], ['product_type', 'Тип комплектуючої', 'text']
          ].map(([name, label, type]) => <label key={name}>{label}<input
            required={name === 'name' || name === 'price'} type={type} step={name === 'price' ? '0.01' : '1'}
            min={type === 'number' ? 0 : undefined} value={form[name]}
            onChange={e => setForm(current => ({ ...current, [name]: e.target.value }))} /></label>)}
          <label className="wide">Опис<textarea rows="2" value={form.description}
            onChange={e => setForm(current => ({ ...current, description: e.target.value }))} /></label>
        </div>
        <div className="actions"><button disabled={saving}>{saving ? 'Зберігаємо…' : editingId ? 'Зберегти зміни' : 'Додати товар'}</button>
          {editingId && <button type="button" className="secondary" onClick={() => { setForm(blank); setEditingId(null) }}>Скасувати</button>}</div>
      </form>
    </section>
    <section className="panel">
      <div className="heading"><h2>Товари <span className="count">{items.length}</span></h2>
        <button type="button" className="secondary" onClick={refresh}>Оновити</button></div>
      {error && <p className="error" role="alert">{error}</p>}
      {loading ? <p>Завантаження…</p> : items.length === 0 ? <p>Товарів поки немає. Додай перший у формі вище.</p> :
        <div className="scroll"><table><thead><tr><th>ID</th><th>Назва</th><th>Категорія</th><th>Ціна</th><th>Залишок</th><th>Дії</th></tr></thead>
          <tbody>{items.map(item => <tr key={item.id}><td>#{item.id}</td><td><strong>{item.name}</strong><small>{item.model}</small></td>
            <td>{item.category || '—'}</td><td>{Number(item.price).toLocaleString('uk-UA')} ₴</td><td>{item.stock_quantity}</td>
            <td className="rowActions"><button type="button" className="secondary" onClick={() => edit(item)}>Змінити</button>
              <button type="button" className="danger" onClick={() => remove(item)}>Видалити</button></td></tr>)}</tbody></table></div>}
    </section>
  </main>
}

createRoot(document.getElementById('root')).render(<App />)
