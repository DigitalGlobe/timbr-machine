import components from '@timbr/react-machine'; 
import JupyterReact from 'jupyter-react-js';
import react from 'react';
import reactDom from 'react-dom';

function load_ipython_extension () {
  requirejs([
      "base/js/namespace",
      "base/js/events",
  ], function( Jupyter, events ) {
      // initialize jupyter react cells, comm mananger and components
      const on_update = ( module, props, commId ) => {
        components.dispatcher.dispatch({
          actionType: module.toLowerCase() + '_update',
          data: props,
          commId
        });
      }
      JupyterReact.init( Jupyter, events, 'timbr.machine', { components, on_update, save: true, react, reactDom } );
  });
}

module.exports = {
  load_ipython_extension: load_ipython_extension
};
