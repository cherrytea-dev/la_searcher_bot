import { createApp } from 'vue'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import Aura from '@primevue/themes/aura'
import App from './App.vue'
import router from './router'

// PrimeVue components
import Button from 'primevue/button'
import Card from 'primevue/card'
import Chip from 'primevue/chip'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import Divider from 'primevue/divider'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Slider from 'primevue/slider'
import Tag from 'primevue/tag'
import ToggleSwitch from 'primevue/toggleswitch'

// Custom components
import AppLayout from '@/components/layout/AppLayout.vue'
import LoadingSpinner from '@/components/common/LoadingSpinner.vue'
import ErrorAlert from '@/components/common/ErrorAlert.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(PrimeVue, {
    theme: {
        preset: Aura,
    },
})

// Register PrimeVue components globally
app.component('Button', Button)
app.component('Card', Card)
app.component('Chip', Chip)
app.component('Column', Column)
app.component('DataTable', DataTable)
app.component('Dialog', Dialog)
app.component('Divider', Divider)
app.component('IconField', IconField)
app.component('InputIcon', InputIcon)
app.component('InputNumber', InputNumber)
app.component('InputText', InputText)
app.component('Message', Message)
app.component('ProgressSpinner', ProgressSpinner)
app.component('Slider', Slider)
app.component('Tag', Tag)
app.component('ToggleSwitch', ToggleSwitch)

// Register custom components globally
app.component('AppLayout', AppLayout)
app.component('LoadingSpinner', LoadingSpinner)
app.component('ErrorAlert', ErrorAlert)
app.component('ConfirmDialog', ConfirmDialog)

app.mount('#app')
